# OUTPUT_SPEC

## Current acquisition outputs (2026-09-20)

当前分工产物位于 `data/derived/distributed/`：

- `plan.json`：固定分工计划，`plan_id` 为 `2f852998f23d432eb45a6c5606f06cfc`。
- `cloud.sqlite`：起点采集状态；`local.sqlite`：晋江采集状态。
- `coordinator.sqlite`：两节点的观测汇总库，仅合并、不采集；后续研究汇总读取此库。
- `validation.json`、`merge_summary.json`、`remerge_summary.json`：本轮验证、合并及重复合并记录；新增数量和核验结果以实际文件及节点 `status` 输出为准。

原 `data/derived/crawler.sqlite` 保留为分工前基线，既有
`data/derived/crawler_export/` 保留为历史导出。新的汇总导出目标为
`data/derived/distributed/export/`。`crawl.py export` 从一致快照生成
`crawler.sqlite`、`works_current.csv`、`dates_current.csv` 和 `summary.json`。
导出库保留 27 张原始历史表、不可变观测、当前元数据和持久任务队列。
`crawl.py audit --previous ...` 比较前一快照并另写验证 JSON。

合并必须保留原观测 UUID、来源、观测时间及节点/计划标记；重复合并不得增加重复
观测或日期证据。源节点执行状态不覆盖汇总库队列；`crawl_merge_log` 记录源快照
状态，汇总库 `summary.json` 的队列计数不代表云端和本地的完成进度。
云端 workflow 尚未发布，本地 `watch` 仅在进程存活时循环，无开机服务。
当前代码验证为 142 项 crawler 测试和 40 项 cloud 测试通过；研究样本和年份覆盖
仍需完成下述实质性试点审计。

## Pilot outputs

1. `data/derived/work_master.csv`
2. `data/derived/source_observation.csv`
3. `data/derived/coverage_by_year_platform.csv`
4. `data/derived/duplicate_id_report.csv`
5. `data/derived/date_quality_report.csv`
6. `analysis_notes/pilot_audit.md`

## Minimum audit table

For each platform × anchor year, report:

- raw records recovered;
- unique work IDs;
- duplicate work IDs;
- share with author IDs;
- share with usable publication year/date;
- share with genre;
- share with status;
- share with resolvable current work pages;
- share with synopsis available;
- collection source and collection date.

## Expansion criterion

Expand from anchor years to the full annual 2010–2025 series only if:

- IDs can be recovered at high rates;
- year/date meaning is documented;
- missingness is not overwhelmingly concentrated in older cohorts;
- duplicate/renamed/reposted works can be flagged rather than silently merged;
- the collection process is reproducible from documented public sources.

No substantive trend graph should be interpreted before this audit is complete.
