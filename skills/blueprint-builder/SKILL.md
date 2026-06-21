---
name: blueprint-builder
stage: 主线与写作产物
trigger: 把已选 storyline 转成段落级 BLUEPRINT.md
description: Use when turning a selected social science paper storyline into a paragraph-level BLUEPRINT.md before drafting or when revising an existing blueprint.
---

# Blueprint Builder

## 用途

用于把已选择的 storyline 转换成可执行的逐段写作计划 `BLUEPRINT.md`。适用阶段是数据探索、文献梳理和 storyline 判断已经相对稳定，但正式成文尚未开始。

blueprint 不是普通 outline。它应该让后续 drafting agent 不再重新发明论文结构，而是按段落功能、证据安排和写作顺序推进。

## 先读什么

优先读取：

1. `Project/harness/PROJECT_CONTEXT.md`
2. `Project/harness/VARIABLES.md`
3. `Project/harness/OUTPUT_SPEC.md`
4. `Project/analysis_notes/INDEX.md`
5. 与当前 storyline 相关的 memo、文献综合、主表和主图

按需读取：

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/writing_style.md
~/.research_harness/shared_rules/literature_taxonomy.md
~/.research_harness/workflows/PIPELINE.md
~/.research_harness/templates/BLUEPRINT_template.md
```

如果 `PROJECT_CONTEXT.md` 已明显过时，先建议更新 storyline，再建立 blueprint。

## 核心规则

`BLUEPRINT.md` 创建并确认后，在以下方面优先于 `PROJECT_CONTEXT.md`：

- 论文结构
- 段落功能
- 写作顺序
- 证据放置
- drafting handoff

但 `BLUEPRINT.md` 不覆盖数据事实、变量定义、样本限制、模型设定或输出格式。这些仍以 `VARIABLES.md`、analysis memos、代码、结果文件和 `OUTPUT_SPEC.md` 为准。

不要默认要求每段目标字数。不要强制每段对应表格或图形。证据挂钩可以是“本节使用哪些结果”或“此段需要哪类证据”。

## blueprint 至少回答什么

每个主要 section 应说明：

- 这个 section 在整篇论文中的功能。
- 它如何服务当前 storyline。
- 它需要哪些证据、文献或概念铺垫。
- 它不能越过哪些证据边界。

每个核心段落应说明：

- Paragraph function
- Core claim
- Internal logic
- Evidence
- Required literature
- Transition
- Avoid

可使用 `BLUEPRINT_template.md`，但不要为了填满模板而制造不存在的内容。

## 构建流程

1. 重述已选择 storyline：经验现象、文献张力、解释逻辑和贡献边界。
2. 设计 section 结构，并说明为何适合该 storyline 和目标期刊。
3. 建立段落级条目；一个段落只承担一个主要功能。
4. 检查主要 claim 是否有证据或文献支撑；不足处标为 open question。
5. 写 drafting handoff note，说明后续写作不能改动什么、哪些 claim 需要谨慎、哪些地方允许风格弹性。

## 各部分写作要求

- Introduction：从经验或理论张力推进到研究问题、文献缺口、数据和贡献；不以空泛时代背景开头。
- Literature Review：按问题、机制和文献对话组织，不逐篇罗列。
- Data and Methods：与 `VARIABLES.md` 保持一致，说明数据、样本、变量、模型和可复现边界。
- Results：先讲发现，再用表图或模型作为证据；不逐个系数机械解释。
- Discussion：回到文献对话和贡献边界，避免把探索性或相关性结果写成强因果结论。

## 常见错误

- 只给 section 标题，缺少段落功能。
- 把 blueprint 写成成稿，提前固定每句话。
- 文献综述脱离结果。
- 结果部分按模型顺序机械罗列，而不是按 storyline 组织。
- 把描述性或相关性证据写成强因果机制。
- 使用标题/摘要层面的文献支持过强 claim。

## 停止条件与交接

可进入成文阶段：全文结构已确认；每个 section 功能明确；主要段落块已写清楚；关键命题有证据或标记为待确认；核心文献与竞争解释已有位置；贡献边界明确；成文 agent 能按蓝图执行而不必重新构思论文。

交接给成文（`workflows/drafting.md`）：已确认的 `BLUEPRINT.md`、必须遵守的主线与结构、必须使用的核心证据与文献、可适度发挥的段落、必须严格按证据写的段落、需避免的过度主张。

## 结束报告

结束时说明：blueprint 是否符合当前 storyline；结构是否有变化；哪些 claim 仍需证据或全文阅读；是否需要更新 `PROJECT_CONTEXT.md`；项目是否可以进入 drafting；建议先写哪一节。
