# AGENTS.md

## 文件定位

这是当前项目的 coding agent 入口文件。它只记录项目读取顺序、执行边界和任务结束汇报要求，不重复全局 harness。

## 先读文件

```text
harness/PROJECT_CONTEXT.md
harness/VARIABLES.md
harness/OUTPUT_SPEC.md
analysis_notes/INDEX.md
```

写作或段落结构任务再读：

```text
draft/outline/BLUEPRINT.md
```

不要默认读取所有 `analysis_notes/round_memos/`。

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

## 数据边界

source data 可能在中央数据仓库，例如：

```text
/Users/wenbohu/课程资料/数据
```

不得修改、覆盖、移动或删除中央数据仓库中的 source data。所有写入操作应发生在项目目录内部，除非用户明确指定其他位置。

## 输出路径

输出路径以 `harness/OUTPUT_SPEC.md` 和项目 README 为准。不得在项目根目录、data、draft、figure、table 等目录中生成散乱 log 或临时文件。

## 执行规则

- 不凭空猜变量含义。
- 不把探索性结果写成最终结果。
- 不未经说明覆盖 final 输出。
- 不把相关性结果写成因果机制。
- 不只说“完成了”，必须说明文件变化。
- 若发现项目文件过时，先报告需要更新什么。

## 上下文优先级

- 用户当前指令优先。
- 项目本地文件优先于全局 harness。
- 数据、变量、样本和模型以 `VARIABLES.md`、代码、结果和 analysis memo 为准。
- 写作阶段中，论文结构、段落功能、写作顺序和证据挂钩以 `BLUEPRINT.md` 为准。

## 任务结束汇报

每次任务结束后说明：修改和生成了哪些文件、保存位置、是否覆盖旧文件、结果是否稳定、哪些地方需要人工判断，以及是否需要更新 `PROJECT_CONTEXT.md`、`VARIABLES.md`、`OUTPUT_SPEC.md` 或 `analysis_notes/INDEX.md`。
