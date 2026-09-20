# Webnovel Stratification Project

## 当前采集架构（2026-09-20，本地已实现）

统一入口为 `code/crawl.py`。当前采用固定分工：云端采起点，本地采晋江，独立保存进度，
再把观测合入本地总库。分工文件为 `data/derived/distributed/plan.json`；
原 `data/derived/crawler.sqlite` 保留为分工前基线，切换后不要再用它采集。
研究对象仍是起点与晋江的作品元数据、目录与日期证据；叙事编码尚未开始。
现阶段起点新目录发现限于已有男频分类；晋江目录按 2005 年至当年分区。
这两个范围都不能代表已经取得全站小说总体。

```text
cloud.sqlite → 起点 worker → 起点观测与持久任务进度
       │                       │
       │ 云端每小批审计、保存   │ 同一分工计划，按观测 ID 去重
       ↓                       ↓
local.sqlite → 晋江 worker → coordinator.sqlite → 完整快照 / CSV / 摘要
                              只汇总，不采集
```

### 优化内容

- **按待办任务续跑**：不再按不断变化的 seed 数量取模轮转；每页、每部分区与作品
  详情都有稳定任务键。预算结束不会标成功；异常退出的租约到期后可恢复。
- **增量采集**：目录发现作品后直接产生详情任务，重复发现不重复排队。任务类型轮转，
  避免只跑目录或只补详情。详情通常 14 天后更新，明确完结作品详情为 90 天；
  起点章节目录目前统一 14 天。首次未处理任务会优先于同优先级的未来刷新任务。
- **两端互不抢任务**：云端仅可领取起点任务，本地仅可领取晋江任务；命令行参数不能
  越过库内分工。每平台串行，请求至少间隔 6 秒，并服从更长的 robots 延时；
  慢响应会延长间隔。robots、会话初始化、重定向都计入预算。
- **失败有状态**：临时断线/5xx 按指数退避，连续 5 次失败转待修复；429、验证页、
  403 等暂停平台。robots 禁止的具体路径不会误停其他允许路径。解析失败保留任务，
  不前移分页。缺库、空库、缺检查点会停止，不自动建立空库覆盖旧状态。
- **自动循环有停止条件**：本地 `watch` 自动跑下一批、等待和续跑；连续三个解析异常
  停止当前批次，存在待修复任务则停止循环。修复后通过明确的 `retry-invalid` 入口重排。
  Ctrl+C 不会被自动循环当成继续运行；休眠超过租约也不使用旧令牌确认任务。
- **分工后可重复合并**：以不可变观测 ID 去重，保留原采集时间和来源；较旧字段不覆盖
  较新字段。不同分工计划、改变过的历史表、相同观测 ID 却内容不同的文件会拒绝合并。
  每个来源库的导入在一个事务中完成，失败整批回滚。
- **准确性与可追溯性**：身份须与页面证据一致；首章首发、平台首发、更新、可见目录端点、
  完结候选分别存储。保留旧观测和字段冲突；较旧来源不覆盖较新已观察字段。
  同一分区不同页重复 ID 序列会拒绝入库。日期证据不自动等于裁决后的研究变量。
- **样本不因缺失被删除**：两库所有平台 ID 均保留；类型标记为 novel_like、non_novel
  或 unresolved，只作待核对标签。研究样本的最终纳入规则仍须单独确定。
- **云端状态长期保存**：每批生成唯一名称的完整快照；先上传快照与审计，再更新指针。
  不再依赖即将过期的 v0.4 Actions artifact，也不每次重下全部历史批次。

### 文件职责

| 文件 | 职责 |
|---|---|
| `code/crawl.py` | 初始化、分工、批次/连续运行、合并、修复重排、状态和审计 |
| `code/crawler_store.py` | 事务、任务租约、来源合并、当前视图与完整快照 |
| `code/crawler_sync.py` | 固定分工库创建、来源快照验证和幂等导入 |
| `code/crawler_http.py` | 允许路径、robots、预算、限速与错误分类 |
| `code/crawler_platforms.py` | 平台适配、分页分区、作品和日期校验 |
| `code/crawler_qidian_html.py` | 起点允许访问的公开分类页解析 |
| `code/cloud_state.py` | 同仓库长期快照、恢复、首次发布与指针更新 |
| `code/cloud_cycle.py` | 每次最多三小批，每批保存成功后再继续 |
| `.github/workflows/webnovel-daily-scheduler.yml` | 起点云端调度 |

原采集器保留为历史代码和纯解析函数来源；后续运行使用新入口。
旧批量入口仍有哈希或终章页面请求逻辑，不在本轮新程序的执行路径内。

### 运行

从仓库根目录运行。使用 Python 3.14 的当前补丁版（本地测试为 3.14.6），
安装项目 `requirements.txt`；`.venv` 已可用。macOS/Linux 可运行。
HTTP 层启动时会自检 robots 通配符和最长路径匹配语义，旧解析器会在联网前停止。

```bash
# 本地晋江有限批次；重复执行自动续跑
.venv/bin/python projects/webnovel_stratification/code/crawl.py run \
  --db projects/webnovel_stratification/data/derived/distributed/local.sqlite --node local \
  --max-requests 50 --max-seconds 300 \
  --summary projects/webnovel_stratification/data/derived/distributed/local_run.json

# 本地连续采集：每批最多 50 次请求/300 秒，批间等待 30 分钟
.venv/bin/python projects/webnovel_stratification/code/crawl.py watch \
  --db projects/webnovel_stratification/data/derived/distributed/local.sqlite --node local \
  --max-requests 50 --max-seconds 300 --interval 1800

# 将两端快照合入总库；重复执行会跳过已合并观测
# 云端发布后，cloud.sqlite 应替换为从同一计划恢复的最新云端快照路径
.venv/bin/python projects/webnovel_stratification/code/crawl.py merge \
  --db projects/webnovel_stratification/data/derived/distributed/coordinator.sqlite \
  --source projects/webnovel_stratification/data/derived/distributed/cloud.sqlite \
  --source projects/webnovel_stratification/data/derived/distributed/local.sqlite \
  --summary projects/webnovel_stratification/data/derived/distributed/merge_summary.json

# 状态与导出
.venv/bin/python projects/webnovel_stratification/code/crawl.py status \
  --db projects/webnovel_stratification/data/derived/distributed/local.sqlite
.venv/bin/python projects/webnovel_stratification/code/crawl.py export \
  --db projects/webnovel_stratification/data/derived/distributed/coordinator.sqlite \
  --out projects/webnovel_stratification/data/derived/distributed/export
```

`run` 默认从数据库读取所属平台，`--node` 用于校验身份；还可用 `--kind` 选择任务类型。
本地进程有互斥锁，同一状态库同时只能运行一个批次；`status` 可在采集中只读查看。
程序支持停止信号；强制终止时
正在执行的任务由下一批在租约过期后重新领取，已提交结果不会丢失。

`watch` 是手动前台入口，需要进程保持运行。长期运行使用下述 macOS 后台服务。
两端可以暂时断联后再合并；合并不复制远端的租约、限流状态
或任务完成状态，因此总库的队列不能用于判断节点执行进度。节点 `owned_jobs` 和
`crawl_merge_log` 中的来源快照状态分别用于查看实时进度与合并时进度。

当前分工已经建立，不必再次执行 `split`。新项目才使用
`crawl.py split --db /path/to/initialized.sqlite --out /path/to/new/distributed`；
拆分会拒绝运行中的旧采集器（含正在等待的 `watch`）。拆分后应停用旧库的采集命令。
修复解析错误后可运行 `retry-invalid --db .../local.sqlite --node local
--kind jjwxc_detail --work-id ID --reason "已修复的具体原因"`；该入口不重置访问限制或已删除页面状态。

### 本地后台服务与停止条件

`code/local_service.py` 生成和控制 `com.huwenbo.webnovel.local` LaunchAgent。
服务配置、暂停原因、运行回执与日志在 `data/derived/distributed/service/`。
默认每 35 分钟启动一批晋江采集，每批最多 50 次请求、300 秒。批间没有爬虫进程
属于正常等待。不要同时手动运行同一个节点的 `watch`。

```bash
# 查看是否已加载后台服务、是否暂停，以及最近一批状态
.venv/bin/python projects/webnovel_stratification/code/local_service.py status \
  --service-dir projects/webnovel_stratification/data/derived/distributed/service

# 主动暂停，重启电脑后仍保持暂停
.venv/bin/python projects/webnovel_stratification/code/local_service.py stop \
  --service-dir projects/webnovel_stratification/data/derived/distributed/service

# 修复问题并重排 invalid 任务后恢复；数据库校验不通过会拒绝恢复
.venv/bin/python projects/webnovel_stratification/code/local_service.py resume \
  --service-dir projects/webnovel_stratification/data/derived/distributed/service
```

| 情况 | 自动行为 | 是否需重新开启 |
|---|---|---|
| 关闭终端或 Codex | 已安装的 launchd 服务继续调度 | 不需要 |
| 电脑休眠、关机或退出登录 | 本地停止工作；唤醒后的后续调度或下次登录再续采，云端不受影响 | 通常不需要，关机后需开机并登录 |
| 单批达到请求/时间上限 | 保存进度，等待下一批 | 不需要 |
| 短暂断网、5xx、限流冷却 | 退避等待，后续批次再尝试 | 通常不需要；同任务连续失败达到上限会转待修复 |
| 页面结构/身份校验失败、数据库损坏、程序内部错误 | 本地写暂停标记；云端遇已有 invalid 时不再请求 | 先修复，再恢复/重排 |
| 403、验证码或持续访问限制 | 暂停受影响平台，不绕过限制 | 持续存在时需人工处理，重启不等于解除限制 |
| 手动 stop 或停用系统后台项目 | 保持暂停或不再调度 | 需要 resume 或重新启用服务 |
| 移动项目、删除环境/状态库、磁盘写满 | 停止并保留可获得的错误信息 | 恢复路径/环境/存储后再启动 |

云端断网、单次 runner 中断等通常由下一次计划运行重新恢复最近已发布的完整快照。
若状态指针损坏、授权失效或 GitHub Actions 被禁用，则需修复云端设置或指针。
GitHub 对公开仓库还有[连续 60 天没有仓库活动自动禁用定时 workflow 的规则](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)；
这种情况需重新启用 workflow，不能把仍在历史列表中的任务视为正在定时采集。

一次性初始化只用于新路径，拒绝覆盖已有库：

```bash
.venv/bin/python projects/webnovel_stratification/code/crawl.py init \
  --db /path/to/new/crawler.sqlite \
  --baseline projects/webnovel_stratification/data/raw/baseline_v04/data/derived/webnovel_catalog.sqlite \
  --live projects/webnovel_stratification/data/raw/cloud_live_20260920/webnovel-latest.sqlite
```

### 真实数据核验

初始化合并得到 **33,742 个平台作品 ID**（晋江 27,916、起点 5,826），
建立 39,599 个初始待办任务，保留 127,524 条章节元数据、94,989 条日期证据。
旧库 27 张表逐行对照均保留；SQLite 完整性与外键检查通过。
19,966 条逐章日期只保留为证据，不提升为作品的单一日期。
迁移后保留的 4 处同时间来源冲突均是晋江外部起始年份冲突，尚未裁决。

三次有限联网批次后，作品 ID 为 **33,795**（比迁移时增加 53），章节元数据为
**128,397**（增加 873）。修正后的第二批两平台各 8 次请求、7 个成功任务，无错误；
第三批继续领取后续任务，一部旧起点作品的详情和目录返回 404，原记录保留。
没有下载章节正文。原试跑中的两处日期格式差异冲突保留在历史诊断中，后续已补等价时间校验。

这些是本轮计数，持续采集后会变化。当前计数以 `status` 和导出摘要为准。
`data/derived/crawler_migration_audit.json` 保存迁移审计；本轮联网批次、续跑及
最终审计证据存放在同一 `data/derived/` 目录。本次完善后 **182 项测试全部通过**
（采集、存储及分工合并 142 项、云端状态和分批运行 40 项）。测试使用模拟响应及本地保存的公开页，
另有真实库和三批联网验证；
不能据此宣称长期运行稳定或全站覆盖完整。

分工架构又进行了本地端到端验证（cloud 角色也在本机执行，尚非云端部署）：
起点新增 3 次观测，晋江新增 4 次观测；合并后共 **33,806 个作品 ID、128,862 条
章节元数据**。与分工前相比增加 11 个作品 ID 和 465 条章节元数据。两个来源再次
导入均新增 0 次观测，作品、章节、日期和观测的标识并集与总库完全一致。
晋江实测遇到作者锁文公告后，修复了被误判为解析失败的问题；修复后的 `watch`
正确记录该任务为当前不可采集，并自动进入下一批采集其他作品。最初失败摘要和
官方响应都保留。核验记录为 `data/derived/distributed/validation.json`，正式导出为
`data/derived/distributed/export/`。历史表数按本次直接查询校正为 27 张，均完整保留。

### 访问与覆盖边界

- 本轮实测起点 robots 禁止 `/webcommon/*` 目录 API。新程序会选择允许访问的
  公开分类 HTML；该页仅是有限列表，标记 `public_html_partial`，不构造隐藏分页，
  不将其声称为完整目录。已有 5,826 个起点 ID 仍可用于允许页面上的详情补全。
- 晋江分类超过可访问页数时，按页面实际提供的筛选项拆分为持久子任务；拆分是否
  穷尽仍待证明，标记 `partitioned_unverified`。拆不下去则保留 `page_limit_unresolved`。
- 验证页、限流、真实身份冲突等仍可能需要人工处理。系统能自动恢复网络类故障，
  不能自行改变平台许可或保证页面结构永不变化。
- `gone` 表示当前页面不可采集，包含 404 和已精确识别的晋江作者锁文公告，不等于
  研究上已确认作品被删除。保留原作品和失败原因；这类任务目前不自动反复重试，
  作者日后解锁的检测仍需另行恢复任务。
- 原始 27 张表是历史研究包；`crawl_*` 是新采集层。新表不能与历史同名概念混用。
  旧版作品日期保留原有来源性质，没有重新宣称为经过当前解析器验证的首发或完结。

### 云端部署状态

新 workflow 已在本地改为每天 03:23、15:23 UTC（台北 11:23、23:23）运行，
沿用同一个并发组，仅采起点；每次最多三批，每批最多 50 次请求、300 秒。
每小批都导出、审计并发布后，才进入下一批，减少云端中断损失。每天理论预算最多
300 次请求，包含 robots 等请求；实际成功采集量受响应速度、冷却和页面状态影响。
恢复错节点、审计或发布失败时停止后续批次。尚未推送、发布初始
快照或替换 main 分支调度。现有线上旧 workflow 仍按原逻辑运行。

首次部署使用 `cloud_state.py bootstrap` 显式发布经过 `audit --node cloud` 审计的
`distributed/cloud.sqlite`，参数包含
`--repo`、`--db`、`--summary`、`--audit`、`--run-id`、`--attempt`、`--target`，
再切换 main 的代码与 workflow。
bootstrap 需要通过审计，并确认远端没有已有指针或旧快照；`--run-id` 使用实际初始化运行标识。日常运行
绝不隐式 bootstrap。GitHub 指针资产替换本身不是原子的：若这一步中断，后续任务
会停止，已经上传的唯一快照仍在，可据此恢复。
本地模拟 cloud 节点的成功运行不等于 GitHub 云端已部署。分工切换需要同时替换旧
线上调度，以免旧程序继续采晋江；发布前不启动长期本地采集。日后可用
`cloud_state.py restore --repo OWNER/REPO --out /new/path/cloud.sqlite --receipt /new/path/restored.json`
取得云端最新快照，再交给上述 `merge --source`。

### 对照的公开实现

采用 Python + SQLite，借鉴成熟爬虫的机制，复用项目已有解析函数：

- [Scrapy 持久任务](https://docs.scrapy.org/en/latest/topics/jobs.html)：任务与去重状态需要跨运行保存；
  本项目将结果、子任务与确认提交放进同一事务，并补异常退出的租约恢复。
- [Scrapy AutoThrottle](https://docs.scrapy.org/en/latest/topics/autothrottle.html)：响应变慢或失败时不加速。
- [Crawlee 持久队列](https://crawlee.dev/python/docs/guides/storages)：抓取状态与生命周期分离。
- [GOLEM 起点采集项目](https://github.com/GOLEM-lab/Qidian_Webnovel_DataCollection)：参考元数据和章节日期组织方式，
  但不沿用硬编码会话与按列表位置拼接日期的方式。
- [notnotype/qidian](https://github.com/notnotype/qidian)：参考目录/详情拆分，补上其简单种子文件之外的事务检查点。

以下保留原研究设计；实际运行和当前数据口径以上述说明为准。

## Goal

Build a reproducible longitudinal bibliography of Chinese web novels, initially covering Qidian and JJWXC from roughly 2010–2025, with the option to push back toward 2005 where source quality permits. The bibliography is the sampling frame for later sociological coding of protagonists' family background, mobility trajectories, resources, meritocratic narratives, inheritance, hidden elite identity, and the legitimation of success.

The first-stage objective is **not** to download as much full text as possible. It is to establish a defensible work-level database with stable platform IDs, dates, metadata provenance, and coverage diagnostics.

## Research design

The database is layered:

1. `work_master`: one row per platform work (`platform + work_id`), containing title, author, date, genre, status, word count, URL, and provenance.
2. `source_observation`: one row per observation of a work in a source or snapshot. This preserves deleted, renamed, re-posted, or otherwise changing works.
3. `text_availability`: records whether synopsis, opening chapters, free chapters, or fuller text are available.
4. `market_visibility`: later stores ranking, recommendation, comments, favorites, or other dated visibility measures.
5. `sociological_coding`: later stores validated narrative measures, separate from raw metadata.

## Immediate pilot

Start with four anchor years: **2010, 2015, 2020, 2025**. For each platform, estimate:

- number of catalog records recovered;
- unique work-ID rate;
- year/date availability;
- duplicate and ambiguous-ID rate;
- missingness by genre and status;
- whether old works still resolve to current pages;
- how much text is available for later narrative coding.

Only after these checks pass should the project expand to every year.

## Directory structure

```text
projects/webnovel_stratification/
├── README.md
├── harness/
│   ├── PROJECT_CONTEXT.md
│   ├── VARIABLES.md
│   └── OUTPUT_SPEC.md
├── analysis_notes/
│   └── INDEX.md
├── code/
│   ├── normalize_catalog.py
│   ├── parse_jjwxc_catalog.py
│   └── audit_catalog.py
├── config/
│   └── source_registry.csv
├── data/
│   ├── raw/
│   └── derived/
└── requirements.txt
```

Raw source files should be treated as immutable. Derived CSV/Parquet files are generated by scripts.

## Core methodological rule

Do not use thematic keywords such as `豪门`, `逆袭`, `真千金`, or `寒门` to define the sampling frame. Those are outcomes to be coded later. The bibliography should be built from platform catalogs or other source-defined universes.

## Ethical / technical rule

Use only publicly accessible pages or data made available for research. Do not bypass authentication, paywalls, CAPTCHAs, access controls, or rate limits. Record source URLs and collection dates so the corpus can be audited.
