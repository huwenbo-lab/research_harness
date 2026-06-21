---
name: storyline-builder
stage: 主线与写作产物
trigger: 比较、筛选、评估论文 storyline
description: Use when constructing, comparing, revising, or evaluating possible storylines for a social science paper after empirical patterns or literature tensions have emerged.
---

# Storyline Builder

## 用途

用于把经验发现、文献张力和理论贡献组织成论文 storyline。适用阶段通常在数据探索和文献梳理之后、`BLUEPRINT.md` 之前。

storyline 不是题目，也不是变量清单，而是一个关于“这个经验模式为什么重要、它推进了哪场学术对话”的结构化判断。

## 先读什么

优先读取：

1. `Project/harness/PROJECT_CONTEXT.md`
2. `Project/harness/VARIABLES.md`
3. `Project/analysis_notes/INDEX.md`
4. 与候选 storyline 相关的 memo、表格、图形和文献综合

按需读取：

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/literature_taxonomy.md
~/.research_harness/shared_rules/writing_style.md
~/.research_harness/workflows/PIPELINE.md
```

如果只读了标题、摘要或探索性结果，必须标明判断的证据等级。

## 好 storyline 的构成

一个可写成论文的 storyline 至少连接：

```text
经验现象
→ 文献或理论张力
→ 可能机制或解释逻辑
→ 数据证据
→ 贡献边界
```

不要只复述数据集、样本或因变量。也不要因为某个结果显著，就自动把它当成主线。

## 产出方式

除非用户已经指定唯一方向，一般比较 2-4 个候选 storyline。每个候选包括：

- 简短名称
- 核心 claim
- 数据支持
- 文献支持
- 理论贡献
- 主要风险
- 还需要补的分析或阅读
- 是否推荐

最终要给出明确判断：推进一个、保留两个竞争方向、先补分析、先补文献，或放弃当前 framing。

## 判断标准

评估时重点看：

- 经验支持是否足够。
- 研究问题是否清楚。
- 文献对话是否真实存在。
- 理论收益是否和证据匹配。
- 是否过度声称机制或因果。
- 是否能组织整篇论文。
- 是否符合目标期刊风格，例如 AJS、ASR 或领域内相近英文期刊。

数据支持较强但理论野心较小的 storyline，通常优于证据支撑不了的大框架。

## 常见风险

- 结果稳定但缺乏理论张力。
- 理论很大但数据支撑很弱。
- 文献对话不清。
- 机制证据不足，却写成机制已被证明。
- 主线过于分散。
- 贡献表述超过数据和方法能够支持的范围。
- 把探索性发现写成最终结果。

## 与项目文件的关系

如果 storyline 被确认或明显调整，应建议更新：

```text
Project/harness/PROJECT_CONTEXT.md
```

只更新当前有效的 storyline、关键经验发现、文献对话、下一步任务和注意事项。不要把所有被淘汰的 storyline 都放进 `PROJECT_CONTEXT.md`。

可保留备选方案在：

```text
Project/draft/revision_notes/storyline_options.md
```

或相关 analysis memo。

## 与 BLUEPRINT.md 的关系

storyline-builder 不负责生成完整逐段写作计划。storyline 确认后，下一步通常是用 `blueprint-builder` 生成或修改 `BLUEPRINT.md`。

进入 blueprint 阶段后，论文结构、段落功能、写作顺序和证据挂钩以 `BLUEPRINT.md` 为准。

## 停止条件与交接

可进入 blueprint 阶段：当前主线能用 2-4 段清楚表达；至少一组稳定结果支撑；文献对话对象已明确；主要竞争解释已识别；贡献边界清楚。

交接给 blueprint（skill `blueprint-builder`）：已选 storyline、核心经验发现、文献对话与核心文献、理论机制、主要表图或结果证据、竞争解释、贡献边界、不应过度主张的内容。

## 结束报告

结束时说明：推荐哪条 storyline；证据强弱在哪里；主要风险是什么；下一步应补分析、补文献还是进入 blueprint。
