# 本地 Research Harness 环境文件修订指南

版本：2026-05-30  
适用范围：个人社会科学研究 harness，用于 Claude Code、Codex 和其他本地 agent 辅助论文项目推进。

这份指南不是新的 harness 设计方案，而是后续修订现有 `research_harness/` 文件夹时的判断标准。目标是让 harness 更像一个可维护的研究工作台：入口清楚、规则轻量、流程可查、细节按需加载、项目层不臃肿。

## 一、联网资料提炼出的核心原则

### 1. 入口文件应是地图，不是百科全书

OpenAI 的 harness engineering 文章明确反对把所有规则都塞进一个巨大的 `AGENTS.md`。原因是上下文稀缺，巨型说明会挤占真实任务、项目代码和相关文档；规则过多也会让 agent 无法判断优先级。更合适的做法是把入口文件做成短地图，指向结构化知识库、workflow、template 和 skill。

转译到本地 harness：`AGENTS.md`、`CLAUDE.md`、`README.md` 不应成为完整操作手册。它们应回答四件事：

- 这个 harness 是做什么的。
- 当前 agent 应先读哪些核心文件。
- 不同任务模式应进入哪个 workflow 或 skill。
- 冲突时按什么优先级判断。

### 2. 指令要分层，越靠近任务越具体

OpenAI Codex 的 `AGENTS.md` 文档、Claude Code memory 文档和 Cursor rules 文档都采用类似思想：全局规则、项目规则、路径规则或本地规则分层加载；越靠近当前工作目录或当前任务的规则越具体。Codex 还明确有全局、项目、嵌套目录的 instruction chain；Claude Code 会沿目录读取 `CLAUDE.md`；Cursor project rules 支持 `.cursor/rules` 和 path patterns。

转译到本地 harness：

- 全局层：只放稳定偏好、研究工作原则、文件地图。
- workflow 层：放阶段性流程，例如文献映射、变量设定、分析规划、结果解读、写作蓝图。
- template 层：放输出形状，不塞长篇教学。
- skill 层：放可重复执行的具体操作步骤、检查清单、脚本说明。
- 项目层：只保留本项目事实、变量、输出标准、分析记录索引和写作蓝图。

### 3. 规则应具体、短、可执行、可检查

OpenAI prompt engineering 和 Claude Code memory 的官方建议都强调清晰、具体、足够上下文、避免模糊。Claude 文档还特别提醒：如果 `CLAUDE.md` 过大或指令冲突，遵循度会下降；多步流程或局部规则应移动到 skill 或 path-scoped rule。

转译到本地 harness：

- 避免“认真分析”“保持高质量”这类不可检查表述。
- 使用“先读 `analysis_notes/INDEX.md`，再按需读取相关 memo”这类可执行规则。
- 使用“默认项目核心文件是四个”这类可检查规则。
- 对必须遵守的文件优先级、数据路径、输出格式要写明确。

### 4. 技能和流程要按需加载，避免启动上下文膨胀

Codex skills 文档把 skill 定义为“任务特定能力”，并说明 Codex 初始只看 skill 的名称、描述和路径，真正使用时再读完整 `SKILL.md`。这就是 progressive disclosure：先给 agent 一张目录，再让它按任务深入读取。

转译到本地 harness：

- `skills/*/SKILL.md` 应各自只负责一个工作。
- skill 的 `description` 要说明何时触发、何时不触发。
- 长步骤、字段解释、示例输出放 skill 或 template，不放全局规则。
- workflow 可以告诉 agent “此时应调用哪个 skill”，但不要复制 skill 的全部内容。

### 5. Harness 的关键不是工具名，而是可见上下文和反馈循环

OpenAI harness engineering 强调：agent 能看到、能验证、能操作的内容才是有效环境。对软件工程来说是代码、测试、日志、指标；对社会科学研究来说，对应的是项目上下文、变量表、输出规范、分析记录索引、文献矩阵、蓝图、结果表和可复现代码。

转译到本地 harness：

- 不要把 Claude/Codex 分工写死成“某工具做某阶段”。
- 先按任务模式判断：文献、变量、分析、结果解释、写作、审查。
- 工具差异只作为执行提示，例如 Codex 更适合本地批量文件修改，Claude Code 更适合长上下文写作讨论。
- 每个 workflow 应有“输入、输出、停止条件、验证方式”。

### 6. 结构化知识库优先于临时聊天记忆

Claude 文档说明 `CLAUDE.md` 和 memory 都是上下文，不是强制配置；OpenAI harness engineering 也强调 repository-local、versioned artifacts 才是 agent 可见的事实来源。

转译到本地 harness：

- 分析历史进入 `analysis_notes/`，由 `analysis_notes/INDEX.md` 管理。
- 当前上下文只保留“现在要做什么”和“必须读取哪些相关记录”。
- 重要决策应进入项目文件或分析 memo，不依赖聊天记录。
- 不新增默认 `STATE.md`、`DECISIONS.md`、`STORYLINE.md` 作为项目核心文件。

## 二、本地 Research Harness 的不可动摇基准

后续修改必须遵守以下基准：

- 这套 harness 以社会科学论文生产流程为中心，不以某个 AI 工具为中心。
- 项目层默认核心文件保持轻量：`PROJECT_CONTEXT.md`、`VARIABLES.md`、`OUTPUT_SPEC.md`、`analysis_notes/INDEX.md`。
- 写作阶段才生成 `BLUEPRINT.md`。
- 进入写作阶段后，`BLUEPRINT.md` 在论文结构、段落功能、写作顺序和证据挂钩方面优先于 `PROJECT_CONTEXT.md`。
- 分析历史保存在 `analysis_notes/`，不要塞进当前上下文。
- 大型公开社会调查数据库默认集中在 `/Users/wenbohu/课程资料/数据`；项目目录只放说明、派生数据、小样本、链接或代码输出。
- 全局规则保持指导性，具体操作细节尽量下沉到 workflow、template 或 skill。

## 三、推荐的文件分层

| 层级 | 文件或目录 | 应承担的职责 | 不应承担的职责 |
| --- | --- | --- | --- |
| 说明入口 | `README.md` | 说明 harness 是什么、如何安装、最小文件集、主要目录 | 详细教 agent 如何完成每个研究任务 |
| 个人画像 | `RESEARCH_PROFILE.md` | 稳定研究偏好、领域、写作偏好、数据位置 | 项目状态、单篇论文当前结论、临时任务 |
| 文件地图 | `FILE_MAP.md`、`TREE.txt` | 帮助人和 agent 快速找到文件 | 复制 workflow 细节 |
| 全局规则 | `shared_rules/*.md` | 稳定、跨项目、短而可执行的原则 | 阶段性流程、长示例、具体字段教学 |
| 工作流 | `workflows/*.md` | 阶段流程、输入输出、停止条件、该读哪些文件 | 大量模板文本、工具专属长说明 |
| 模板 | `templates/*.md` | 项目文件和产物的结构骨架 | 把每个项目都强行填成同一种内容 |
| 技能 | `skills/*/SKILL.md` | 可重复任务的具体操作、检查、脚本说明 | 宏观价值宣言、项目事实 |
| Agent 入口 | `agent_entries/global/CLAUDE.md`、`agent_entries/global/AGENTS.md` | 工具可读的短入口和路由 | 完整复制所有全局规则 |
| 项目层模板 | `templates/project_CLAUDE_template.md`、`templates/project_AGENTS_template.md` | 项目本地入口，说明本项目该读什么 | 重复全局 harness 全部内容 |

## 四、详细程度与语言风格标准

### 1. 整体详细程度

这套 harness 需要“足够具体”，但不追求“所有事情都预先写完”。判断标准不是文件越多越好，也不是每个文件越短越好，而是每类文件是否承担了自己的职责。

软性篇幅目标如下：

| 文件类型 | 建议详细程度 |
| --- | --- |
| `README.md` | 人类可读的总入口和安装地图；如果包含目录树，约 200-350 行可以接受。 |
| `FILE_MAP.md` | 每个文件一行说明，通常控制在 100 行以内。 |
| `TREE.txt` | 只放文件树，不写解释。 |
| `RESEARCH_PROFILE.md` | 稳定研究偏好和工作习惯，不放当前项目历史。 |
| `shared_rules/*.md` | 每个主题约 50-120 行；只保留跨项目稳定原则。 |
| `workflows/*.md` | 每个 workflow 约 80-180 行；包含输入、步骤、输出、停止条件和交接。 |
| `templates/*.md` | 每个模板约 40-140 行；只给结构和占位符，不写成长案例。 |
| `skills/*/SKILL.md` | 每个 skill 约 80-220 行；放具体流程和检查，长例子下沉到 `references/`。 |
| `agent_entries/global/*.md` | 约 80-120 行；只放读取顺序、任务路由和优先级。 |
| 项目 `CLAUDE.md`/`AGENTS.md` 模板 | 约 40-80 行；只放本项目读取顺序和本地覆盖规则。 |
| 修订指南或 reference 文件 | 可以更长，但不能作为默认启动上下文；超过 100 行时要有清楚标题结构。 |

如果一个文件明显超过目标，先问：它是否在做另一个文件类型的工作。例如，`shared_rules` 如果开始写一长串操作步骤，应转到 workflow 或 skill；`AGENTS.md` 如果开始解释每个模板字段，应转到 template 或 guide。

### 2. 语言风格

本 harness 的默认语言是中文，文件名、命令、字段名、工具名和受控标签保留英文。语言应像研究者给本地 agent 的工作说明，而不是企业级 AI 框架文档。

推荐写法：

- 用短句和直接动词：先读、检查、输出、不要、只有在……时。
- 写可执行规则：`先读 analysis_notes/INDEX.md，再按需读取相关 memo`。
- 写可检查标准：`项目层默认核心文件是四个`。
- 保留社会科学论文生产词汇：研究问题、变量、机制、经验策略、文献对话、结果解释、段落功能。
- 用平铺 bullet，不做深层嵌套；需要复杂结构时拆成小节。

避免写法：

- 抽象宣言：例如“全面提升研究质量”“确保学术严谨”。
- 工具中心语言：例如“Claude 负责理论、Codex 负责代码”。
- 企业框架腔：例如“构建端到端智能体治理体系”。
- 过度承诺：例如“自动完成论文生产闭环”。
- 无法检查的软要求：例如“写得更好”“充分考虑所有因素”。

更好的替代表述：

```text
不要写：保持高质量文献综述。
改成：文献综述必须区分 core_conversation、theoretical_anchor、empirical_precedent、institutional_background、competing_explanation 和 uncertain。

不要写：全面记录分析过程。
改成：每轮模型调整后在 analysis_notes/ 中新增 memo，并在 analysis_notes/INDEX.md 中登记。

不要写：Claude 和 Codex 各自承担固定阶段。
改成：按任务模式选择 workflow；工具名称只影响执行方式，不决定研究分工。
```

### 3. AI 友好写作规范（逐文件改写时遵循）

把上面的语言风格落成可执行清单，逐文件改写时照此执行。让 AI 稳定理解意图、输出符合预期，靠的是祈使、可检查、结构化，不靠语言。

**语言约定**

- 指令、推理、研究判断用中文；文件名、字段名、受控标签、命令用英文（如 `PROJECT_CONTEXT.md`、`core_conversation`、`stage`、`code/logs/`）。
- 技能 `description`（frontmatter）用英文、第三人称、`Use when …` 句式，并含触发关键词。
- 写作风格规则的示例用目标语言：中文论文规则给中文范例，英文论文规则给英文范例。
- 每个文件挑一个主语言，不在同一文件内中英无规律混杂。
- 不为"更像官方"把整套切英文。

**语气与结构**

- 祈使优先，一条指令一行：写"先读 X；再做 Y；不要 Z"，不写"本阶段的目标是通过……"。
- 规则前置、理由后置或省略：先给 directive，再（可选）补一句为什么。
- 可检查优先于抽象：写"表必须是三线表""log 必须在 `code/logs/`"，不写"保持高质量""认真分析"。
- 结构化、可扫读：成段叙述拆成 bullet、编号步骤、清单或表；一个小节只讲一件事。
- 入口与总图只做路由，细节留在 workflow / skill / template。

**给示例**

- 对格式关键、容易跑偏的规则（文件名、表格形态、claim 写法、目录结构），给一个"好 / 坏"对照例，胜过单纯描述。

**逐文件改写清单**

改每个文件时自问：

- 每条规则是否祈使、能否检查？
- 是否把描述性叙述压成了 bullet / 步骤 / 表？
- 语言是否一致（主语言 + 英文受控词）？
- 该文件是否只承担自己那一层的职责（见“三、推荐的文件分层”）？
- 格式关键处是否给了正反例？
- 是否与其它文件重复或矛盾（同一规则只留一个权威来源）？

### 4. 模板案例对本地 harness 的启发

联网检查到的 `AGENTS.md`、Claude `CLAUDE.md`、Cursor rules 和 Codex skills 案例共同指向一个原则：默认入口要短，专门知识要分层，具体流程要按需加载。

本地已经新增维护 skill：

```text
research_harness/skills/harness-maintainer/
  SKILL.md
  references/template-patterns.md
```

后续修改 harness 本身时，应优先读取这个 skill。它把官方模板案例转译成适合本地社会科学 Research Harness 的维护流程、篇幅标准和语言风格标准。

## 五、具体修改指南

### 1. 压缩 agent 入口文件

适用文件：

- `research_harness/agent_entries/global/CLAUDE.md`
- `research_harness/agent_entries/global/AGENTS.md`
- `research_harness/templates/project_CLAUDE_template.md`
- `research_harness/templates/project_AGENTS_template.md`

建议做法：

- 入口文件优先写“读取顺序”和“任务模式路由”。
- 避免复制 `shared_rules/`、`workflows/`、`skills/` 的详细内容。
- 同一条原则只保留一个权威来源，入口文件只引用。
- 对 Claude/Codex 的差异只写执行提示，不写死研究阶段归属。
- 如果未来采用 Claude Code 的导入机制，可考虑让项目 `CLAUDE.md` 引入 `AGENTS.md` 后再补充 Claude 专属规则，减少双维护。

建议目标：

- 全局 agent 入口控制在约 80-120 行。
- 项目 agent 入口控制在约 40-80 行。
- 任一入口文件不应出现长字段表、完整 workflow 或长模板。

### 2. 让全局规则只保留稳定原则

适用目录：

- `research_harness/shared_rules/`

建议做法：

- `workflow_principles.md` 作为优先级和阶段关系的唯一权威来源。
- `literature_taxonomy.md` 只维护文献角色分类和矩阵最小字段。
- `code_style.md` 只写跨语言代码组织原则；Stata、R、表格导出等细节放 skill 或 workflow。
- `writing_style.md` 只写学术写作偏好和审稿标准，不写段落逐句模板。

判断标准：

- 如果一条规则只在某个阶段适用，放 workflow。
- 如果一条规则描述“怎么操作”，放 skill。
- 如果一条规则描述“产物长什么样”，放 template。
- 如果一条规则跨所有项目、所有阶段都有效，才留在 shared rule。

### 3. workflow 应写成阶段性作业单

适用目录：

- `research_harness/workflows/`

每个 workflow 建议保持同一结构：

- 适用场景：何时使用。
- 先读文件：固定入口和按需读取来源。
- 输入：用户需要提供什么，项目已有文件提供什么。
- 操作步骤：阶段性步骤，不写过度细节。
- 输出：应更新或生成哪些文件。
- 停止条件：做到什么程度可以交付。
- 交接提示：下一阶段应看哪些文件。

本地特别规则：

- 文献类 workflow 默认先读 `analysis_notes/INDEX.md`，再读相关 memo，不默认吞入所有历史。
- 分析类 workflow 不假设 raw data 在项目目录；优先检查 `/Users/wenbohu/课程资料/数据` 或项目上下文中的数据说明。
- 写作类 workflow 必须说明：写作阶段 `BLUEPRINT.md` 优先于 `PROJECT_CONTEXT.md`。

### 4. template 应保留弹性，不替研究者做内容判断

适用目录：

- `research_harness/templates/`

建议做法：

- 模板只规定必要字段和信息结构。
- 不默认要求每段目标字数。
- 不强制每段绑定图表。
- 不要求固定段落数量，除非是明确期刊格式或用户要求。
- 字段要少而稳定，避免为了“完整”增加低频字段。

对 `BLUEPRINT_template.md` 的原则：

- 应保留论文结构、段落功能、写作顺序、证据挂钩。
- 可以标注“可能使用的证据/表图/模型结果”。
- 不应要求每段都有目标字数或强制对应表图。

### 5. skill 应专注于一个可重复任务

适用目录：

- `research_harness/skills/`

建议做法：

- 每个 `SKILL.md` 的描述必须清楚说明触发条件。
- 一个 skill 只负责一个任务，例如“文献矩阵构建”“Stata 代码风格检查”“项目初始化”。
- skill 中可以写具体步骤、检查清单、命令模板、脚本约定。
- 如果某个 skill 开始覆盖多个研究阶段，应拆分，或把宏观部分上移到 workflow。

建议格式：

```markdown
---
name: skill-name
description: 何时使用；何时不使用。
---

## 读取上下文

## 操作步骤

## 输出

## 检查
```

### 6. 项目层保持轻量

新建论文项目时，默认只生成：

- `PROJECT_CONTEXT.md`
- `VARIABLES.md`
- `OUTPUT_SPEC.md`
- `analysis_notes/INDEX.md`

进入写作阶段后再生成：

- `BLUEPRINT.md`

可选文件只在需要时生成：

- `literature_matrix.*`
- `analysis_plan.md`
- `results_interpretation.md`
- `draft_sections/`
- `revision_notes/`

不建议默认生成：

- `STATE.md`
- `DECISIONS.md`
- `STORYLINE.md`
- 大型 raw data 副本
- 一堆空的阶段文件

### 7. 数据路径要符合真实工作流

本地默认判断：

- 大型公共调查数据：`/Users/wenbohu/课程资料/数据`
- 项目内：只放数据说明、派生数据、小样本、清洗结果、代码、输出表图。
- 任何 workflow 或 template 不应默认要求 `data/raw/` 下有完整原始数据。

建议在项目 `PROJECT_CONTEXT.md` 中写：

```markdown
## 数据来源

- 原始数据主路径：/Users/wenbohu/课程资料/数据/...
- 本项目使用的数据子集：
- 项目内派生数据路径：
- 不复制原始数据到项目目录，除非用户明确要求。
```

### 8. 历史记录用索引管理，不进入启动上下文

推荐结构：

```text
analysis_notes/
  INDEX.md
  2026-05-30_variable_decision.md
  2026-05-31_model_check.md
  2026-06-02_results_interpretation.md
```

`INDEX.md` 应记录：

- memo 文件名
- 日期
- 主题
- 对应研究阶段
- 是否仍然有效
- 下次读取建议

agent 默认只读 `INDEX.md`。只有当当前任务需要时，再读取相关 memo。

### 9. 建立明确的冲突处理顺序

建议统一写入 `shared_rules/workflow_principles.md`，并在 agent 入口中引用：

1. 用户当前明确指令优先。
2. 项目本地文件优先于全局 harness。
3. 写作阶段中，`BLUEPRINT.md` 对结构和段落安排优先于 `PROJECT_CONTEXT.md`。
4. `PROJECT_CONTEXT.md` 负责项目事实；`VARIABLES.md` 负责变量定义；`OUTPUT_SPEC.md` 负责目标期刊和输出规范。
5. 历史 memo 只作为证据和背景，不能自动覆盖当前项目文件。
6. 工具名称不决定任务分工；任务模式优先。

## 六、下一轮本地修改优先级

### P0：巩固入口文件的“地图化”

建议检查并继续压缩：

- `research_harness/agent_entries/global/CLAUDE.md`
- `research_harness/agent_entries/global/AGENTS.md`
- `research_harness/templates/project_CLAUDE_template.md`
- `research_harness/templates/project_AGENTS_template.md`

目标是让这些文件只负责路由和优先级，不复制 workflow 细节。

### P1：把 `workflow_principles.md` 做成唯一优先级来源

建议检查：

- 是否已在 `workflows/PIPELINE.md` 明确各阶段与承担文件（workflow 或 skill）的关系。
- 是否已经明确 `BLUEPRINT.md` 的写作阶段优先级。
- 是否已经明确项目层默认四个核心文件。
- 是否已经明确分析历史读取策略。

如果这些规则散落在多个文件中，应保留一个权威表述，其他地方只引用。

### P2：继续降低 shared rules 的操作手册感

重点检查：

- `shared_rules/code_style.md`
- `shared_rules/writing_style.md`
- `shared_rules/literature_taxonomy.md`

如果出现长步骤、长示例、阶段流程，应下沉到 workflow、template 或 skill。

### P3：为 Cursor 添加可选规则，而不是默认引入

如果你未来常用 Cursor，可以新增：

```text
research_harness/agent_entries/cursor/
  project_rules_overview.md
  rules/
    research-harness-core.mdc
    stata-analysis.mdc
    writing-blueprint.mdc
```

但不建议现在默认加入 `.cursor/rules/` 到每个项目。原因是当前 harness 的主要目标是跨 Claude Code、Codex 和本地 agent 通用；Cursor 规则应作为可选适配层。

## 七、修订审查清单

每次修改 harness 文件前，先用这组问题检查：

- 这条规则是否跨所有项目和阶段都有效？如果不是，不放 shared rules。
- 这段内容是否是具体操作步骤？如果是，优先放 skill。
- 这段内容是否是产物结构？如果是，优先放 template。
- 这段内容是否只服务某个研究阶段？如果是，放 workflow。
- 入口文件是否仍然能在 1-2 分钟内读完？
- 是否把历史分析塞进了当前上下文？
- 是否默认生成了不必要的动态项目文件？
- 是否把工具名当成任务分工依据？
- 是否假设 raw data 在项目目录内？
- 是否出现已放弃规则，例如默认“测量与方法文献”、过宽文献矩阵字段、`BLUEPRINT.md` 每段目标字数、强制段落对应图表？

## 八、参考来源

本指南依据以下官方或一手资料整理，并按本地社会科学研究场景转译：

- OpenAI Codex: Custom instructions with `AGENTS.md`  
  https://developers.openai.com/codex/guides/agents-md
- AGENTS.md open format  
  https://agents.md/  
  https://github.com/agentsmd/agents.md
- OpenAI: Harness engineering, leveraging Codex in an agent-first world  
  https://openai.com/index/harness-engineering/
- OpenAI: Unlocking the Codex harness, how we built the App Server  
  https://openai.com/index/unlocking-the-codex-harness/
- OpenAI Codex: Agent Skills  
  https://developers.openai.com/codex/skills
- Anthropic Claude Code: How Claude remembers your project  
  https://code.claude.com/docs/en/memory
- Anthropic Claude: How Claude Code works in large codebases  
  https://claude.com/blog/how-claude-code-works-in-large-codebases-best-practices-and-where-to-start
- Cursor Docs: Rules  
  https://docs.cursor.com/context/rules
- OpenAI API: Prompt engineering  
  https://developers.openai.com/api/docs/guides/prompt-engineering
