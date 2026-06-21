# OVERVIEW.md — Research Harness 现状总览

一页看懂这套 harness：定位、分层、研究流水线对应文档、项目层、后台脚本。维护规则见 `HARNESS_ENVIRONMENT_FILE_REVISION_GUIDE.md`；文件定位与“任务 → skill 路由”见 `FILE_MAP.md`；设计理由与演进见顶层《个人社会科学研究 Harness 项目书》。

## 定位

面向社科论文生产（社会学、人口学、家庭、分层、生命历程、调查研究）的本地研究工作台。工具中立：Claude Code、Codex 等共享同一套规范。源在 `research_harness/`，一句 `scripts/sync_to_global.sh` 下发到 `~/.research_harness/` 与各工具入口。

## 三层 + 后台

- 全局层：我如何做研究（`RESEARCH_PROFILE.md` ＋ `shared_rules/`）。
- 流水线层：研究阶段如何推进、用什么（`workflows/` ＋ `skills/`）。
- 项目层：单篇论文的轻量档案（`PROJECT_CONTEXT.md` 等）。
- 后台：脚本（同步、体检、自动生成），平时不碰。

## 读取顺序

1. 入口 `~/.claude/CLAUDE.md` 或 `~/.codex/AGENTS.md`（只做路由）。
2. `README.md` ＋ `FILE_MAP.md`。
3. 按当前阶段在 `workflows/PIPELINE.md` 找承担者；要 skill 就按 `FILE_MAP.md` 的“任务 → skill 路由”读对应 `SKILL.md`。
4. 进具体项目再读项目层文件。

## 研究流水线 → 对应文档

总图：`workflows/PIPELINE.md`。八个任务阶段：

| 阶段 | 文档 / 技能 |
| --- | --- |
| ①a 探索分析 ＋ 问题磨尖 | `workflows/data_exploration.md` ＋ `stata-socialscience-analysis`、`questionnaire-to-variables`、`analysis-memo-maintainer` |
| ①b 主分析 ＋ 稳健性 | 同上 ＋ `sociology-table-output` |
| claim 校准（能 / 不能主张） | analysis memo ＋ `PROJECT_CONTEXT.md` 必填栏 |
| ② 文献定位 | `workflows/literature_mapping.md` ＋ `literature-map-builder`、`citation-snowballing` |
| ③ storyline | `skills/storyline-builder` |
| ④ blueprint | `skills/blueprint-builder` ＋ `templates/BLUEPRINT_template.md` |
| ⑤ 照蓝图成文 | `workflows/drafting.md` ＋ `sociology-table-output`、`academic-writing-style-control` |
| ⑥ fresh-context 修订 | `skills/fresh-context-revision` |
| ⑦ 最终检查 | `skills/final-checker` |
| ⑧ 审稿回应 R&R | `workflows/r_and_r.md`（专门技能待建） |

前三段（问题 ↔ 数据 ↔ 文献）来回打圈，不是直线。写作阶段，论文结构以已确认的 `BLUEPRINT.md` 为准。

## 项目层（每篇论文）

默认核心：`harness/PROJECT_CONTEXT.md`、`harness/VARIABLES.md`、`harness/OUTPUT_SPEC.md`、`analysis_notes/INDEX.md`；写作期再加 `draft/outline/BLUEPRINT.md`。原始大数据在 `/Users/wenbohu/课程资料/数据`，不复制进项目。初始化用 `skills/project-harness-initializer`。

## 后台脚本（在工作区 `scripts/`，不下发）

| 脚本 | 作用 |
| --- | --- |
| `sync_to_global.sh` | 下发；推送前自动重生成 TREE 和路由；覆盖全局入口前备份并防误覆盖（`--dry-run` / `--force`） |
| `check_harness.sh` | 体检：陈旧规则扫描 ＋ TREE/路由是否最新 |
| `gen_tree.sh` / `gen_filemap_router.sh` | 自动生成 `TREE.txt` / FILE_MAP 路由 |
| `set_data_path.sh` | 一条命令改数据仓库路径 |

## 单一真相源

- `TREE.txt` 和 FILE_MAP 路由自动生成，不手写（改 skill 的 `stage`/`trigger` frontmatter，路由自动更新）。
- 数据仓库路径内联在用到它的文件里（让 agent 就地看到）；要改时用 `set_data_path.sh` 一条命令全改。
- 同一规则只留一个权威来源，其它引用。
