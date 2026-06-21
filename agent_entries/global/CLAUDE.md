# Global rules for Claude Code

## My preferences
- 默认用中文解释，除非用户要求英文。回答应具体、直接、可执行，避免泛泛赞美。

## Research harness
- 仅当任务涉及社会科学研究项目、数据分析、Stata/R、文献、表图、论文写作、修订或 harness 维护时，才读取 `~/.research_harness/`。
- 不要启动时全量读取 harness；先读 `~/.research_harness/README.md` 和 `~/.research_harness/FILE_MAP.md`，再按任务读取相关文件。
- 进入具体研究项目后，优先读 `harness/PROJECT_CONTEXT.md`、`harness/VARIABLES.md`、`harness/OUTPUT_SPEC.md` 和 `analysis_notes/INDEX.md`；写作阶段再读 `draft/outline/BLUEPRINT.md`。
- 不要默认读取全部 `analysis_notes/` memo；根据 `analysis_notes/INDEX.md` 选择相关 memo。
- 需要 skill 时，先查 `~/.research_harness/FILE_MAP.md` 的“任务 → skill 路由”，找到匹配项后只读取该 skill 的 `SKILL.md`，不要全量加载。
- 大型公开社会调查数据库可能在 `/Users/wenbohu/课程资料/数据`；不要默认把项目 `data/` 当作 raw data 唯一来源。
- `BLUEPRINT.md` 只规定写作结构和段落顺序，不覆盖变量、样本、模型、数据事实或输出格式。
- 中文学术表达参考《社会学研究》《社会》《社会学评论》；英文写作参考 AJS、ASR、Demography、Social Forces、PDR 和 ESR。
