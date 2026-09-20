# PROJECT_CONTEXT

## Current execution state (2026-09-20)

采集入口为 `code/crawl.py`。已完成节点分工，持久状态位于
`data/derived/distributed/`：`cloud.sqlite` 固定负责起点（`qidian`），
`local.sqlite` 固定负责晋江（`jjwxc`），`coordinator.sqlite` 仅汇总、不采集。
分工记录在同目录 `plan.json`，当前 `plan_id` 为
`2f852998f23d432eb45a6c5606f06cfc`。

`data/derived/crawler.sqlite` 保留为分工前基线，后续研究汇总读取
`data/derived/distributed/coordinator.sqlite` 中的 `crawl_*` 表。各节点均保留
原始基线的 27 张表。新采集观测记录 `collector_node` 和 `collection_plan`；
合并保留原观测 UUID、来源与观测时间，重复合并不会重复生成观测或日期证据。
源节点的租约、完成状态和限速状态不导入汇总库；汇总库队列不是云端或本地的
执行进度，源快照的队列与平台状态另由 `crawl_merge_log` 记录。

云端 workflow 的本地代码已更新，尚未发布。本地 `watch` 只在进程存活期间
自动循环，尚无开机服务。代码验证已通过 142 项 crawler 测试和 40 项 cloud 测试。
真实节点试跑、合并和重复合并的最新结果，以节点 `status` 输出及
`data/derived/distributed/` 中的 `validation.json`、`merge_summary.json`、
`remerge_summary.json` 为准；汇总导出目标为该目录下的 `export/`。
采集计数尚不构成最终小说样本或已验证的年份覆盖；锚点年份有效性审计与实质编码
仍待开展。运行命令、日期语义和未解决覆盖问题见 README。

## Working title

Who Gets to Succeed? Long-Term Change in Status Attainment Narratives in Chinese Web Fiction

## Core question

How have Chinese web novels changed in the kinds of people portrayed as capable of success, the resources that enable success, and the grounds on which status and privilege are represented as deserved?

## Empirical scope

Primary platforms: Qidian and JJWXC.

Target period: 2010–2025, with exploratory extension toward 2005 if catalog coverage and date validity permit.

## Stage 1: bibliography construction

Create a longitudinal sampling frame independent of the substantive hypotheses. The first database should identify works, authors, dates, genres, status, word counts, URLs, and provenance. It should preserve multiple observations of the same work across sources.

## Stage 2: text linkage

For works in the bibliography, record availability of synopsis, opening chapters, free chapters, continuous chapters, authorized research corpora, and other auditable text sources.

## Stage 3: sociological coding

Develop and validate measures of:

- protagonist's family-of-origin resources;
- upbringing conditions versus latent/biological family status;
- initial occupational/class position;
- individual effort, education, skill, talent, institutional credentials;
- family resources, inheritance, kinship, marriage, patronage, and elite networks;
- hidden identity / restoration of status;
- genuine upward mobility versus restoration of an ascribed status;
- narrative legitimation of inequality and success.

## Key design distinction

Supply and visibility are separate outcomes. A publication-cohort database measures what is produced. Historical rankings, recommendations, comments, or favorites measure cultural visibility. Do not treat current cumulative popularity as historical popularity.

## Current pilot decision

Audit four anchor years first: 2010, 2015, 2020, 2025. Expand to annual coverage only after checking date validity, work-ID stability, missingness, and old-work survival.
