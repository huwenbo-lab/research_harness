---
name: analysis-memo-maintainer
stage: 数据与变量
trigger: 创建、更新或索引 analysis memo
description: Use when creating, updating, indexing, or reviewing analysis memos during iterative empirical analysis in a social science research project.
---

# Analysis Memo Maintainer

## 用途

用于维护 `analysis_notes/` 中的分析历史。它帮助 agent 记录数据探索、模型尝试、失败路线、结果解释变化和后续判断，同时避免把历史过程塞进当前上下文。

核心边界：

```text
PROJECT_CONTEXT.md = 当前项目状态
analysis_notes/ = 分析历史与迭代记录
```

## 先读什么

每轮分析开始时，先读：

1. `Project/analysis_notes/INDEX.md`
2. `Project/harness/PROJECT_CONTEXT.md`
3. `Project/harness/VARIABLES.md`
4. 与本轮相关的代码、表格、图形或旧 memo

只有当任务涉及代码规范或输出规范时，再读：

```text
~/.research_harness/shared_rules/code_style.md
~/.research_harness/workflows/data_exploration.md
```

不要因为存在旧 memo 就全部读入；通过 `INDEX.md` 判断哪些 memo 相关。

## 什么时候创建 memo

以下情况应创建或更新 memo：

- 新模型设定、因变量、样本限制或变量构造。
- 主要表格、主要图形、稳健性检验、异质性分析或机制分析。
- 失败但值得记住的尝试。
- 结果解释、storyline 或后续策略发生变化。

很小的代码格式修改不需要 memo，除非影响解释、样本、变量或输出结果。

## memo 放哪里

默认放在：

```text
analysis_notes/round_memos/
```

文件名应简短、可追踪：

```text
2026-06-01_r01_descriptive.md
2026-06-03_r02_main_models.md
2026-06-05_r03_failed_interactions.md
```

避免 `memo_new.md`、`analysis_final.md`、`notes2.md` 这类名字。

## memo 内容

使用项目模板 `analysis_memo_template.md`。没有模板时，至少包含：

- 本轮目的
- 数据、样本和代码位置
- 运行了什么
- 主要发现
- 失败尝试及原因
- 对 storyline 或下一轮分析的影响
- 生成文件
- 是否需要更新 `PROJECT_CONTEXT.md`
- 是否已更新 `analysis_notes/INDEX.md`

失败尝试要记录“为什么不采用”，不要只写“结果不好”。

## 更新 INDEX.md

每个重要 memo 完成后更新 `analysis_notes/INDEX.md`。索引只写摘要，不复制 memo 内容。它的功能是帮助后续 agent 决定该读哪个 memo。

推荐保留字段：

```text
Date | Round | Memo file | Topic | Main takeaway | Still valid? | Avoid repeating
```

## 何时提升到 PROJECT_CONTEXT.md

只有仍然约束当前项目的结论才提升到 `PROJECT_CONTEXT.md`，例如：

- 主分析结果稳定，可能进入论文。
- 某变量不适合作为核心变量。
- 某样本限制成为默认设定。
- 某模型成为主模型。
- 某结果改变了 storyline。

不要把历史细节、已放弃路线或临时探索都写进 `PROJECT_CONTEXT.md`。

## 结束报告

结束时说明：创建或更新了哪个 memo；是否更新 `INDEX.md`；是否有内容需要提升到 `PROJECT_CONTEXT.md`；未来 agent 应避免重复哪条路线。
