# Research Harness README

## 文件定位

这是个人社会科学研究 Harness 的总入口。它说明 harness 的用途、文件分层、推荐读取顺序、项目初始化方式和维护原则。

这套 harness 面向社会学、人口学、婚姻家庭、社会分层、生命历程、调查研究和相关经验社会科学论文生产。它不是一组孤立 prompt，也不是以某个 AI 工具为中心的配置包，而是围绕论文生产流程组织的本地研究工作台。

## 核心原则

- 研究工作流优先于工具名称。Claude Code、Codex、ChatGPT 或其他本地 agent 可以共享同一套规范。
- 全局文件回答“我如何做研究”；项目文件回答“这个项目现在是什么状态”；workflow 和 skill 回答“某类任务如何完成”。
- 项目层保持轻量。默认核心文件是 `PROJECT_CONTEXT.md`、`VARIABLES.md`、`OUTPUT_SPEC.md` 和 `analysis_notes/INDEX.md`。
- 写作阶段再生成 `BLUEPRINT.md`。进入写作阶段后，论文结构、段落功能、写作顺序和证据挂钩以已确认的 `BLUEPRINT.md` 为准。
- 分析历史保存在 `analysis_notes/`，不要塞进当前上下文。
- 全局规则保持指导性；具体步骤下沉到 `workflows/`、`templates/` 或 `skills/`。

## 推荐安装位置

建议将全局 harness 放在：

```text
~/.research_harness/
```

推荐结构：

```text
~/.research_harness/
├── README.md
├── OVERVIEW.md
├── FILE_MAP.md
├── INSTALL_OR_COPY_INSTRUCTIONS.md
├── HARNESS_ENVIRONMENT_FILE_REVISION_GUIDE.md
├── RESEARCH_PROFILE.md
├── shared_rules/
├── workflows/
├── templates/
├── skills/
└── agent_entries/
```

完整文件清单见 `FILE_MAP.md` 和 `TREE.txt`。

## 文件分层

### 全局层

```text
RESEARCH_PROFILE.md
shared_rules/
```

记录长期稳定偏好和跨项目原则，不写入具体项目的变量、模型、结果或文献细节。

### Workflow 层

```text
workflows/
```

说明研究阶段如何推进，例如数据探索、文献映射、storyline 构建、blueprint 建立、成文、fresh-context 修订和最终检查。

Workflow 文件用于阶段流程和交接，不保存项目状态。

### Template 层

```text
templates/
```

提供项目文件和论文产物的结构骨架。模板只规定必要字段和占位结构，不替具体项目预写结论。

### Skill 层

```text
skills/
```

保存可重复任务的执行说明，例如 Stata 分析、表格输出、文献矩阵构建、blueprint 构建、写作风格控制和 harness 维护。

### Agent 入口层

```text
agent_entries/global/
```

提供 Claude Code、Codex 或其他 agent 可读取的入口文件候选版本。入口文件应像地图，负责读取顺序、任务路由和优先级，不复制全部规则。

### 项目层

每个研究项目推荐保留轻量 harness：

```text
Project_Name/
├── harness/
│   ├── PROJECT_CONTEXT.md
│   ├── VARIABLES.md
│   └── OUTPUT_SPEC.md
├── analysis_notes/
│   └── INDEX.md
├── README.md
├── CLAUDE.md
└── AGENTS.md
```

其他目录按项目需要建立，例如 `code/`、`data/derived/`、`draft/`、`figure/`、`table/` 和 `literature/`。

## 推荐读取顺序

Agent 处理全局 harness 或新项目初始化时，先读：

```text
README.md
OVERVIEW.md
RESEARCH_PROFILE.md
FILE_MAP.md
shared_rules/workflow_principles.md
workflows/PIPELINE.md
```

处理具体项目时，先读：

```text
Project/README.md
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/harness/OUTPUT_SPEC.md
Project/analysis_notes/INDEX.md
```

进入写作阶段后，再读：

```text
Project/draft/outline/BLUEPRINT.md
```

然后根据任务选择相应 workflow 或 skill。

## 新项目初始化

最小初始化只需要：

```text
harness/PROJECT_CONTEXT.md
harness/VARIABLES.md
harness/OUTPUT_SPEC.md
analysis_notes/INDEX.md
README.md
CLAUDE.md
AGENTS.md
```

建议从 `templates/` 复制对应模板。不要在项目开始时默认创建 `STATE.md`、`DECISIONS.md`、`STORYLINE.md` 或一组空的阶段文件。

`BLUEPRINT.md` 只在项目进入写作蓝图阶段后创建：

```text
draft/outline/BLUEPRINT.md
```

## 数据管理原则

大型公开社会调查数据库和长期数据资产通常集中存放在中央数据仓库，例如：

```text
/Users/wenbohu/课程资料/数据
```

项目目录中的 `data/` 通常保存派生数据、临时数据、变量字典和项目分析数据，不默认保存完整 raw data。

AI 可以读取中央数据仓库中的 source data，但不得修改、覆盖、移动或删除原始数据。所有写入操作应发生在项目目录内部，除非用户明确指定其他位置。

## 上下文优先级

1. 用户当前明确指令优先。
2. 项目本地文件优先于全局 harness。
3. 数据事实、变量定义、样本范围和模型设定以 `VARIABLES.md`、代码、结果文件和 analysis memo 为准。
4. 写作阶段中，结构、段落功能、写作顺序和证据挂钩以 `BLUEPRINT.md` 为准。
5. 历史 memo 只作为背景和证据，不能自动覆盖当前项目文件。
6. 工具名称不决定任务分工；任务模式优先。

## 使用 Claude Code 与 Codex

Claude Code 和 Codex 应共享同一套研究规范。工具差异只影响执行方式，不决定研究阶段归属。

常见倾向：

- Claude Code 更适合长上下文讨论、storyline、blueprint、写作和审稿人式批评。
- Codex 更适合本地文件修改、代码执行、批量处理、表格图形输出和 harness 维护。

如果任务模式与工具默认倾向冲突，以任务模式为准。

## 维护原则

维护 harness 本身时，优先使用：

```text
skills/harness-maintainer/SKILL.md
HARNESS_ENVIRONMENT_FILE_REVISION_GUIDE.md
```

不要为了完整而过度维护文件。只有反复出现的问题才沉淀到 shared rule、workflow、template 或 skill 中。

如果 AI 反复犯同类错误：

- 研究判断问题进入 `RESEARCH_PROFILE.md` 或 `shared_rules/workflow_principles.md`。
- 代码问题进入 `shared_rules/code_style.md` 或相关 Stata skill。
- 表格图形问题进入 `shared_rules/table_figure_style.md` 或 table skill。
- 文献分类问题进入 `shared_rules/literature_taxonomy.md` 或 literature skill。
- 写作问题进入 `shared_rules/writing_style.md` 或 writing style skill。

## 最小可用版本

最小可用版本包括：

```text
RESEARCH_PROFILE.md
shared_rules/workflow_principles.md
shared_rules/code_style.md
shared_rules/table_figure_style.md
shared_rules/literature_taxonomy.md
shared_rules/writing_style.md
workflows/PIPELINE.md
workflows/data_exploration.md
workflows/literature_mapping.md
workflows/drafting.md
workflows/r_and_r.md
templates/PROJECT_CONTEXT_template.md
templates/VARIABLES_template.md
templates/OUTPUT_SPEC_template.md
templates/analysis_notes_index_template.md
templates/BLUEPRINT_template.md
skills/storyline-builder/SKILL.md
skills/blueprint-builder/SKILL.md
skills/fresh-context-revision/SKILL.md
skills/final-checker/SKILL.md
skills/harness-maintainer/SKILL.md
```

其他 skill 和模板可按项目需要逐步补齐。
