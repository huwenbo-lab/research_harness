# VARIABLES

## Current acquisition layer (2026-09-21)

下文原有表定义继续作为历史研究规格。当前采集使用
`data/derived/distributed/{cloud,local,coordinator}.sqlite` 中的 `crawl_*` 表，
其中 cloud 只采起点、local 只采晋江，coordinator 只合并两者的观测。
后续汇总以 `coordinator.sqlite` 为准；原 `data/derived/crawler.sqlite`
保留为分工前基线，原始 27 张表保持不变。

| Table / field | Current meaning |
|---|---|
| `crawl_works` | One current row per `(platform, work_id)`; field provenance and extra metadata remain in JSON |
| `sample_class` | Preliminary genre-based label, not the final inclusion rule; missing genre stays unresolved |
| `crawl_observations` | 不可变解析结果、来源 URL、观测时间和覆盖状态；合并保留源行的 `observation_id`、`recorded_at`、`observed_at`、`observed_ts`、`time_basis`、`source_kind` 和 `result_json`；历史导入的未知观测时间不补造 |
| `result_json.meta.collector_node`, `result_json.meta.collection_plan` | 分工后新采集观测的来源节点（`cloud` / `local`）及计划 ID；当前计划为 `2f852998f23d432eb45a6c5606f06cfc` |
| `crawl_meta`（键 `distribution_plan`、`node_id`） | 固定平台归属计划及本库角色；计划原件见 `data/derived/distributed/plan.json` |
| `crawl_date_evidence` | All observed/source dates, including chapter-level dates; not all are work publication dates |
| `crawl_work_dates` | One current value per work and date role, with source and basis; conflicting evidence remains retained |
| `crawl_chapters` | 历史章节元数据保留；2026-09-21 切换作品级范围后不再新增逐章记录 |
| `collection_scope` | `work_date_endpoints` 表示采作品信息和有限日期端点；记录在 `crawl_meta`、新观测 meta 和状态摘要中 |
| `crawl_jobs` | 旧起点章节待办标记 `excluded` 并保留退出事件，由 `qidian_dates` 日期端点任务接续； 本库持久任务队列；合并可以生成后续任务，但不复制源节点的租约、完成状态或执行次数；coordinator 队列不表示节点执行进度 |
| `crawl_pages` | 分页观测证据；`unresolved` 不表示目录覆盖已完成 |
| `crawl_merge_log` | 每次合并的来源节点、计划、来源文件路径、合并时间与新增/已知观测数；`source_queue_json`、`source_platforms_json` 保留源快照的执行状态，不代表实时状态 |

新范围的 `metadata_json.publication_window` 保存首个可见章、正文起止候选与最后可见章，
每个端点均含标题、URL 和分开的首发/更新时间。`boundary_status` 为待复核候选或未确定，
`directory_coverage` 明确目录尚未独立核验。没有首章编号不能判为作品首章；末尾番外不等于正文。
`main_text_start_publication_candidate`、`main_text_end_publication_candidate` 为正文起止首发候选；
对应 `*_update_candidate` 仅表示修改时间。章节标题无法验证正文内容，不能直接构造实际写作期。
正文起止以最新 `publication_window` 为准；日期表保留历史角色，后续证据不足不自动清空旧候选。

Date roles distinguish `catalog_publication`, `platform_publication`,
`first_chapter_publication`, `last_update`, and `completion_candidate`.
`first_observed_chapter_publication`, `last_observed_chapter_publication`, and
`last_observed_chapter_update` describe the visible directory endpoints, not
necessarily the original first chapter, final chapter, or whole-work update.
Older imported date roles retain their original interpretation; they were not
all independently validated by the new collector. Equivalent complete timestamps
at the same precision are compared without changing their raw representation;
a platform-page timestamp without a timezone is interpreted as UTC+08 for that
comparison. Dates, years and different precision levels stay distinct. A completion candidate is
never automatically promoted to a verified completion date.

Qidian's display word counts may be rounded in units of ten thousand; the
HTML adapter preserves `word_count_raw` and `word_count_is_approximate`.

## A. work_master

Primary key: `platform + work_id`.

| Variable | Meaning |
|---|---|
| platform | `qidian` / `jjwxc` |
| work_id | Stable platform work/novel ID where available |
| title_current | Current observed title |
| author_name_current | Current observed author name |
| author_id | Stable platform author ID where available |
| first_pub_date_raw | Raw platform/source date string |
| first_pub_date | Parsed date if defensible |
| first_pub_year | Parsed year if defensible |
| date_type | `platform_publication`, `first_chapter_update`, `snapshot_presence`, `external_bibliography`, etc. |
| date_confidence | `high`, `medium`, `low`, `unresolved` |
| genre_major | Platform major genre/category |
| genre_minor | Platform subgenre/category |
| audience_channel | Platform-defined channel if available; do not infer reader gender |
| status | serializing / completed / paused / other raw category |
| word_count | Observed word count |
| work_url | Canonical work URL |
| first_seen_source | Source used to create master record |
| first_seen_at | Research collection date |
| last_seen_at | Latest research collection date |

## B. source_observation

One row per work-source observation. Primary key can be a generated `observation_id`.

Required fields: `platform`, `work_id`, `source_name`, `source_url`, `snapshot_date`, `title_observed`, `author_observed`, `date_raw`, `genre_raw`, `status_raw`, `word_count_raw`, `retrieval_status`, `collection_timestamp`, `raw_file`.

This table should retain contradictory or changing information rather than silently overwriting it.

## C. text_availability

Fields: `platform`, `work_id`, `synopsis_available`, `opening_chapters_available`, `free_chapters_available`, `continuous_text_available`, `full_text_available`, `text_source`, `license_or_access_note`, `checked_at`.

Availability does not imply permission to redistribute text.

## D. market_visibility (future)

Possible fields: `platform`, `work_id`, `observation_date`, `ranking_type`, `rank`, `votes`, `comments`, `favorites`, `recommendation_slot`, `source_url`.

## E. sociological_coding (future)

Keep substantive coding separate from metadata. Initial candidate dimensions:

- `protagonist_upbringing_class`
- `biological_family_class`
- `usable_family_resources_at_start`
- `education_credential_role`
- `effort_role`
- `talent_role`
- `institutional_route_role`
- `family_resource_role`
- `inheritance_role`
- `marriage_role`
- `patronage_role`
- `hidden_elite_identity`
- `status_restoration`
- `genuine_upward_mobility`
- `success_legitimation_type`
- `coding_evidence_location`
- `coder_method`
- `coding_confidence`

Do not collapse upbringing conditions, biological family status, and usable resources into a single family-background variable during the first coding pass.
