# Global rules for codex
## Operating principles- Prefer small, reviewable diffs. Avoid sweeping refactors unless explicitly requested.- Before editing, identify the file(s) to change and state the plan in 3-6 bullets.- Never invent APIs, configs, or file paths. If unsure, search the repo first.- Keep changes consistent with existing style and architecture.
## Safety and secrets- Never paste secrets, tokens, private keys, .env values, or credentials into code or logs.- If a task requires secrets, ask me to provide them via environment variables.- Do not add analytics, telemetry, or network calls unless I ask.
## Code quality bar- Add or update tests for behavior changes when the project has tests.- Prefer type safety and explicit error handling.- Add comments only when the intent is non-obvious.
## Build and run etiquette- If you need to run commands, propose the exact command and why.- When you make changes that may break build, run the fastest relevant check first.
## Output formatting- For code changes: include a short summary + list of files changed.- For debugging: include hypotheses, experiments run, and the minimal fix.
## My preferences- I like concise explanations, concrete steps, and copy-pastable commands.- Default language for explanations: Chinese.

## Research harness
- 默认输出语言为中文。除非用户明确要求英文，说明文档、维护报告、workflow/template/skill 说明和项目 harness 文件都应以中文为主；文件路径、命令、字段名、skill name、YAML frontmatter 和期刊名可保留英文。
- 仅当任务涉及社会科学研究项目、数据分析、Stata/R、文献、表图、论文写作、修订或 harness 维护时，才读取 `~/.research_harness/`。
- 不要启动时全量读取 harness；先读 `~/.research_harness/README.md` 和 `~/.research_harness/FILE_MAP.md`，再按任务读取相关文件。
- 进入具体研究项目后，优先读 `harness/PROJECT_CONTEXT.md`、`harness/VARIABLES.md`、`harness/OUTPUT_SPEC.md` 和 `analysis_notes/INDEX.md`；写作阶段再读 `draft/outline/BLUEPRINT.md`。
- 不要默认读取全部 `analysis_notes/` memo；根据 `analysis_notes/INDEX.md` 选择相关 memo。
- 需要 skill 时，先查 `~/.research_harness/FILE_MAP.md` 的“任务 → skill 路由”，找到匹配项后只读取该 skill 的 `SKILL.md`，不要全量加载。
- 大型公开社会调查数据库可能在 `/Users/wenbohu/课程资料/数据`；不要默认把项目 `data/` 当作 raw data 唯一来源。
- `BLUEPRINT.md` 只规定写作结构和段落顺序，不覆盖变量、样本、模型、数据事实或输出格式；不默认创建 `STATE.md`、`DECISIONS.md` 或 `STORYLINE.md`。
