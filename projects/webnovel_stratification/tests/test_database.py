"""Offline regression checks. Run after acquiring artifacts and building the database."""
import hashlib,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code'))
from build_database import platform_id,unit_number,read_csv
from collect_catalog import parse_jjwxc,access_problem
class ParserTests(unittest.TestCase):
    def test_category_link_not_id(self):
        self.assertIsNone(platform_id('//www.qidian.com/xuanhuan','qidian'))
        self.assertEqual(platform_id('https://www.qidian.com/book/1010868264/','qidian'),'1010868264')
        self.assertEqual(platform_id('//book.qidian.com/info/1010868264','qidian'),'1010868264')
        self.assertIsNone(platform_id('https://www.qidian.com.evil.invalid/book/1010868264/','qidian'))
    def test_large_id_is_string(self):
        self.assertEqual(platform_id('https://www.qidian.com/book/12345678901234567/','qidian'),'12345678901234567')
    def test_units(self):
        self.assertEqual(unit_number('731.48万'),7314800)
        self.assertIsNone(unit_number('未知'))
    def test_multiline_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'f.csv';p.write_text('id,description\n123,"a\nb"\n',encoding='utf-8')
            self.assertEqual(read_csv(p)[0]['description'],'a\nb')
    def test_real_catalog(self):
        p=ROOT/'data/raw/pilot/jjwxc_catalog.html'
        if not p.exists():self.skipTest('Pilot raw file not supplied')
        rows,m=parse_jjwxc(p.read_bytes(),'https://www.jjwxc.net/bookbase.php?orderstr=1','test')
        self.assertEqual(len(rows),100);self.assertEqual(len({r['work_id'] for r in rows}),100)
        self.assertEqual(m['current_page'],1);self.assertEqual(m['year_fields'][2010],{'name':'fbsj2010','value':'2010'})
        self.assertEqual(rows[0]['work_id'],'3200611');self.assertIsNone(rows[0]['first_pub_year_verified'])
    def test_annual_years_and_hashes(self):
        fs=list((ROOT/'data/raw').rglob('jjwxc_observations.jsonl'));checked=set()
        if not fs:self.skipTest('Annual artifact not supplied')
        for p in fs:
            for line in p.read_text().splitlines():
                r=json.loads(line);self.assertEqual(r['declared_pub_year'],r['requested_year'])
                f=p.parent/r['raw_file']
                if f not in checked:
                    self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),r['raw_sha256']);checked.add(f)
        self.assertGreater(len(checked),0)
    def test_login_page_rejected(self):
        p=ROOT/'data/raw/annual/jjwxc_2009_p00025.html'
        if not p.exists():self.skipTest('Login-page evidence not supplied')
        self.assertEqual(access_problem(p.read_bytes()),'authentication_required')
class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=ROOT/'data/derived/webnovel_catalog.sqlite'
        if not p.exists():raise unittest.SkipTest('Build the database first')
        cls.db=sqlite3.connect(f'file:{p}?mode=ro',uri=True)
    @classmethod
    def tearDownClass(cls):cls.db.close()
    def test_integrity(self):
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_unique_platform_ids(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM (SELECT platform,platform_work_id FROM work_master GROUP BY 1,2 HAVING count(*)>1)').fetchone()[0],0)
    def test_no_invented_first_pub_years(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM work_master WHERE first_pub_year_verified IS NOT NULL').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM source_observation WHERE date_type!="platform_catalog_publication" AND declared_pub_year IS NOT NULL').fetchone()[0],0)
    def test_synthetic_exclusion(self):
        self.assertEqual(self.db.execute('SELECT sum(excluded_rows) FROM quarantine WHERE reason="synthetic_frontend_test_data"').fetchone()[0],1920)
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_visibility WHERE source_week_label IN ("2026-W20","2026-W21")').fetchone()[0],0)
    def test_no_fabricated_coding(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM sociological_coding').fetchone()[0],0)
    def test_full_text_access_unknown(self):
        self.assertEqual(self.db.execute('SELECT sum(full_text_acquired) FROM text_availability').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM text_availability WHERE online_full_text_access!="not_checked"').fetchone()[0],0)
    def test_mapping_conflict_retained(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM crosswalk WHERE mapping_status="duplicate_qidian_mapping_needs_review"').fetchone()[0],2)
    def test_exact_release_counts(self):
        self.assertEqual(self.db.execute('SELECT count(*) FROM work_master').fetchone()[0],8554)
        self.assertEqual(self.db.execute('SELECT sum(accepted_observations) FROM annual_coverage WHERE platform="jjwxc"').fetchone()[0],2200)
        self.assertEqual(self.db.execute('SELECT count(*) FROM historical_recommendation_distinct').fetchone()[0],4002)
if __name__=='__main__':unittest.main(verbosity=2)
