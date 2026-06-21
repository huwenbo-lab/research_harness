# drafting.md

## 适用场景

用于 `BLUEPRINT.md` 已生成并经研究者确认之后的成文阶段。AI 的任务是按蓝图逐节、逐段生成论文草稿。

本阶段核心原则是执行，不是重新构思。AI 可以优化表达、句间衔接和局部段落节奏，但不应擅自改变已确认的文章结构、段落功能、论证顺序和核心 storyline。

## 先读文件

先读全局规则：

```text
RESEARCH_PROFILE.md
shared_rules/workflow_principles.md
shared_rules/writing_style.md
```

再读项目文件：

```text
Project/draft/outline/BLUEPRINT.md
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/harness/OUTPUT_SPEC.md
Project/literature/synthesis/literature_synthesis.md
Project/literature/matrix/literature_matrix.xlsx
Project/table/final/
Project/figure/final/
```

按需读取 analysis memo 或 exploratory 表图，但必须标记其不稳定性。

## 上下文优先级

写作阶段中，论文结构、段落功能、写作顺序和证据挂钩以已确认的 `BLUEPRINT.md` 为准。`PROJECT_CONTEXT.md` 主要作为项目背景和研究判断来源。

`BLUEPRINT.md` 不能覆盖数据事实、变量定义、样本范围、模型设定和输出格式。涉及这些内容时，应回到 `VARIABLES.md`、analysis memo、代码、结果文件和 `OUTPUT_SPEC.md`。

## 输入

每次成文任务应明确：

- 本次写哪一节或哪些段落；
- 对应的 `BLUEPRINT.md` 段落块；
- 使用哪些文献、表格、图形或模型结果；
- 输出语言和目标期刊风格；
- 哪些结论需要谨慎表述；
- 输出保存位置。

不建议一次性生成全文。优先按 section 或 subsection 逐步写作。

## 步骤

1. 读取对应蓝图片段。确认段落功能、核心命题、证据和必须避免的表述。
2. 检查证据可用性。若蓝图要求的结果、引用或变量说明缺失，应先反馈，不要编造。
3. 生成段落草稿。每段只完成蓝图规定的功能。
4. 自查蓝图偏离。若为连贯性做了小幅调整，应明确说明。
5. 标记待确认事项。对未 final 的表图、待补全文文献或不稳定结果保持谨慎。
6. 保存或输出草稿，并说明下一步建议。

## 成文规则

- 严格遵守段落功能。不要把经验张力段写成文献综述，也不要把结果段写成宽泛讨论。
- 保持概念稳定。核心概念应与 `PROJECT_CONTEXT.md`、`VARIABLES.md` 和 `BLUEPRINT.md` 一致。
- 结果解释受证据约束。不要把描述性结果写成因果结论，不要把相关性写成机制证明。
- 引用服务论证。每个引用都应有明确功能，例如理论机制、已有发现、竞争解释或背景。
- 风格服从 `shared_rules/writing_style.md` 和 `OUTPUT_SPEC.md`。不要在 workflow 中维护重复期刊清单。

## 分节提示

- Introduction: 围绕问题提出、经验张力、文献缺口和本文贡献展开。不要以空泛背景开头。
- Literature Review: 按文献脉络和研究缺口组织，不逐篇罗列。
- Data and Methods: 说明数据来源、样本构造、变量操作化和模型设定，并与 `VARIABLES.md` 一致。
- Results: 先讲核心发现，再引用表格或图形。不要逐个系数机械解释。
- Discussion: 回到研究问题和文献对话，说明推进了什么、限制在哪里、哪些结论不能外推。

## 输出

分节草稿：

```text
Project/draft/sections/
```

完整草稿：

```text
Project/draft/full_draft/
```

试写或修改说明：

```text
Project/draft/revision_notes/
```

文件名应简洁可追踪，例如 `intro_draft.md`、`litreview_draft.md`、`results_draft.md`、`discussion_draft.md`。不要使用 `new.docx` 或 `draft_final_final.md`。

## 停止条件

一次 drafting 任务结束时，应满足：

- 本次要求的 section 或段落已完成；
- 段落功能与 `BLUEPRINT.md` 对齐；
- 引用、表图和结果未被编造；
- 过度结论已降调或标记；
- 需要确认的问题已列出。

## 交接

交给 fresh-context 修订阶段（skill `fresh-context-revision`）时，应提供：

- 本次草稿位置；
- 使用的蓝图片段；
- 偏离蓝图的地方及原因；
- 未确认的表图、变量、文献或结果；
- 希望修订者重点检查的语言、结构、论证或证据问题。
