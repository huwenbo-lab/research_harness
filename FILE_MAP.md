# FILE_MAP.md

## Root

- `README.md`: 总入口地图，说明 harness 的用途、分层、读取顺序、项目初始化和维护原则。
- `OVERVIEW.md`: 一页现状总览——分层、研究流水线对应文档、项目层、后台脚本。
- `RESEARCH_PROFILE.md`: 研究者长期画像，记录稳定研究偏好、数据原则、代码偏好、文献偏好和写作偏好。
- `HARNESS_ENVIRONMENT_FILE_REVISION_GUIDE.md`: 维护和修改 harness 本身的指南，包含文件详细程度、语言风格和后续修订原则。
- `INSTALL_OR_COPY_INSTRUCTIONS.md`: 安装全局 harness、配置 agent 入口和初始化项目的操作说明。
- `FILE_MAP.md`: 当前文件；只提供文件定位，不重复 workflow 或 skill 细节。
- `TREE.txt`: 当前 harness 文件树快照。

## shared_rules/

- `workflow_principles.md`: workflow 关系、上下文优先级、项目层轻量原则和任务模式优先规则。
- `code_style.md`: Stata/R 代码、数据路径、log、analysis memo 和 production code 的跨项目原则。
- `table_figure_style.md`: 表格、回归表、图形、caption、文件命名和 draft 输出原则。
- `literature_taxonomy.md`: 文献功能分类、文献矩阵最小字段和标题摘要层级检索边界。
- `writing_style.md`: 中文和英文学术写作的总体风格原则。

## workflows/

- `PIPELINE.md`: 研究流水线总图——五阶段顺序、各阶段读什么/产出/交接、由哪个 workflow 或 skill 承担。
- `data_exploration.md`: 数据探索、模型迭代和 analysis memo 工作流。
- `literature_mapping.md`: 文献检索、文献矩阵和文献综述备忘录工作流。
- `drafting.md`: 按 `BLUEPRINT.md` 逐节成文的工作流。
- `r_and_r.md`: 投稿后审稿回应（R&R）——拆解意见、补分析、改稿和 response 信。

storyline、blueprint、fresh-context 修订、最终检查四个阶段已并入对应 skill（见上方“任务 → skill 路由”）。

## templates/

- `PROJECT_CONTEXT_template.md` -> `Project/harness/PROJECT_CONTEXT.md`
- `VARIABLES_template.md` -> `Project/harness/VARIABLES.md`
- `OUTPUT_SPEC_template.md` -> `Project/harness/OUTPUT_SPEC.md`
- `analysis_notes_index_template.md` -> `Project/analysis_notes/INDEX.md`
- `analysis_memo_template.md` -> `Project/analysis_notes/round_memos/`
- `BLUEPRINT_template.md` -> `Project/draft/outline/BLUEPRINT.md`
- `project_readme_template.md` -> `Project/README.md`
- `project_CLAUDE_template.md` -> `Project/CLAUDE.md`
- `project_AGENTS_template.md` -> `Project/AGENTS.md`

## skills/（任务 → skill 路由）

按当前任务模式选择 skill；找到匹配项后只读该 skill 的 `SKILL.md`，不要全量加载。下表由 `scripts/gen_filemap_router.sh` 从各 skill 的 frontmatter（`stage` / `trigger`）自动生成，请勿手改标记之间的内容。

<!-- BEGIN AUTOGEN: skill-router -->
数据与变量
- 创建、更新或索引 analysis memo → `analysis-memo-maintainer/`
- 把问卷、codebook、题项整理成变量说明（VARIABLES.md） → `questionnaire-to-variables/`
- 写/改/审 Stata 或 R 分析代码、做分析、写 analysis memo → `stata-socialscience-analysis/`

文献
- 已确定核心文献后做参考文献追踪和被引追踪 → `citation-snowballing/`
- 从标题摘要库检索、分类、做文献矩阵与 synthesis → `literature-map-builder/`

主线与写作产物
- 中/英文学术写作风格控制、去 AI 腔 → `academic-writing-style-control/`
- 把已选 storyline 转成段落级 BLUEPRINT.md → `blueprint-builder/`
- 生成/评估表格、回归表、图形、caption（论文 draft 风格） → `sociology-table-output/`
- 比较、筛选、评估论文 storyline → `storyline-builder/`

修订与检查
- 投稿前或阶段性提交前综合检查 → `final-checker/`
- 新上下文修订、蓝图偏离与证据边界检查 → `fresh-context-revision/`

项目与维护
- 维护或修改 Research Harness 本身 → `harness-maintainer/`
- 初始化或改造项目级轻量 harness → `project-harness-initializer/`

<!-- END AUTOGEN: skill-router -->

## agent_entries/global/

- `CLAUDE.md`: Claude Code 全局入口候选文件。
- `AGENTS.md`: Codex 或其他 coding agent 全局入口候选文件。
