# CLAUDE.md

## 文件定位

这是当前项目的 Claude Code 入口文件。它只记录项目读取顺序、任务模式和特殊注意事项，不重复全局 harness。

## 先读文件

先读项目核心文件：

```text
harness/PROJECT_CONTEXT.md
harness/VARIABLES.md
harness/OUTPUT_SPEC.md
analysis_notes/INDEX.md
```

写作阶段再读：

```text
draft/outline/BLUEPRINT.md
```

不要默认读取所有 `analysis_notes/round_memos/`。先根据 `analysis_notes/INDEX.md` 判断需要哪一份 memo。

## 全局参考

按任务需要读取：

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/workflow_principles.md
~/.research_harness/shared_rules/code_style.md
~/.research_harness/shared_rules/table_figure_style.md
~/.research_harness/shared_rules/literature_taxonomy.md
~/.research_harness/shared_rules/writing_style.md
~/.research_harness/workflows/
~/.research_harness/skills/
```

## 当前阶段

```text
[数据探索 / 文献定位 / storyline 构建 / blueprint 建立 / 照蓝图成文 / fresh-context 修订 / 最终检查]
```

## 当前任务

1. 
2. 
3. 

## 任务模式路由

- 数据探索：`workflows/data_exploration.md`
- 文献定位：`workflows/literature_mapping.md`
- storyline：skill `storyline-builder`
- blueprint：skill `blueprint-builder`
- 成文：`workflows/drafting.md`
- fresh-context 修订：skill `fresh-context-revision`
- 最终检查：skill `final-checker`
- 阶段总图与交接：`workflows/PIPELINE.md`

## 上下文优先级

- 用户当前指令优先。
- 项目本地文件优先于全局 harness。
- 数据、变量、样本和模型以 `VARIABLES.md`、代码、结果和 analysis memo 为准。
- 写作阶段中，论文结构、段落功能、写作顺序和证据挂钩以 `BLUEPRINT.md` 为准。

## 项目特殊注意事项

- 目标期刊或写作语言：
- 数据来源：
- 易误解变量：
- 不能重复尝试的分析路线：
- 当前重要表图：
- 尚未确定的问题：

## 与 Codex 协作

Claude Code 和 Codex 应共享项目主线、变量定义、文件结构和输出规范。任务模式比工具名称更重要。

如果 Codex 生成了代码、表格、图形或 analysis memo，应根据需要更新 `PROJECT_CONTEXT.md` 或 `analysis_notes/INDEX.md`。
