---
name: fresh-context-revision
stage: 修订与检查
trigger: 新上下文修订、蓝图偏离与证据边界检查
description: Use when reviewing or revising a draft in a new, clean context after it was generated from a blueprint — diagnosing AI style, structure, argument, and evidence-boundary problems from a detached editor/reviewer stance, deliberately not inheriting the drafting conversation. Not for continued drafting or expansion.
---

# fresh-context-revision

## 用途

草稿照蓝图写出后，在新的、干净的上下文里审查或修订它时用。针对一个常见 AI 写作问题：生成草稿的模型往往看不见自己的语言惯性、过度顺滑、连接词重复、空过渡或过度自信的 claim。所以要以更抽离的编辑/审稿人视角来诊断和修订。

## 先读文件

只读评估需要的文件：

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/writing_style.md
~/.research_harness/workflows/PIPELINE.md
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/harness/OUTPUT_SPEC.md
Project/draft/outline/BLUEPRINT.md
Project/draft/full_draft/
```

核查经验 claim 时，再读相关表格、图形、analysis memo 或代码输出。不要继承整个写作对话——重点是和写作上下文拉开距离。

## 核心原则

fresh-context revision 不是继续写，而是诊断、批评和受控修订。评估四个维度：

```text
语言
结构
论证
证据边界
```

草稿可能语言顺但结构弱、可能清楚但过度主张、可能照了蓝图但读着像 AI 生成。把它们当不同问题处理。

## 修订流程

1. 先诊断再改写。判断主要问题是 AI 腔、段落功能、概念漂移、证据越界还是结构。
2. 对照 `BLUEPRINT.md`。草稿偏离蓝图时，判断偏离是否合理；不合理就建议拉回蓝图。
3. 检查证据边界。草稿用强因果/机制语言但证据不足时，下调 claim。
4. 选择性修订。未要求不全文重写。优先高杠杆段落：开头段、贡献段、文献缺口段、结果总结段、讨论开头。

## 常见 AI 写作症状

英文里注意：

```text
overuse of smooth but empty transitions
repeated therefore / moreover / furthermore
overuse of important / crucial / complex / multifaceted
three-part abstract noun strings
paragraphs that restate rather than advance
claims that sound stronger than evidence
generic contribution language
excessively balanced but noncommittal sentences
```

中文里注意：

```text
“具有重要意义”
“提供了新的视角”
“值得注意的是”
“复杂而多元”
“深刻影响”
“在一定程度上”
“从某种意义上说”
```

这些不必然错，但重复或无支撑时常是 AI 腔信号。

## 中文修订标准

向《社会学研究》《社会》《社会学评论》靠：问题意识清楚、概念稳定、论证有纪律、claim 节制。除非用户要，不要改成政策报告、媒体评论或面向公众的散文。

## 英文修订标准

向 AJS、ASR、Demography、Social Forces、Population and Development Review、European Sociological Review 靠。优先清晰 claim、稳定概念、节制的因果语言、期刊式段落推进。避免泛泛打磨的 AI 散文。

## 输出格式

### 诊断报告

审一节或全文时用：

```markdown
## 总体诊断

## 语言问题

## 结构问题

## 论证问题

## 证据边界问题

## 优先修订

## 需要重写的段落
```

### 对照修订

改选定段落时用：

```markdown
## 原文问题

## 修订后

## 为什么这样改

## 仍存风险
```

### 蓝图合规检查

用户想知道草稿是否照蓝图时用：

```markdown
## 蓝图合规

## 偏离

## 合理的偏离

## 有问题的偏离

## 对 BLUEPRINT.md 的建议更新
```

## 何时更新项目文件

- 草稿暴露出蓝图本身有问题时，建议更新 `BLUEPRINT.md`。
- 草稿把实际论文 storyline 稳定下来、且与 `PROJECT_CONTEXT.md` 不一致时，建议用最终蓝图或草稿反向更新 `PROJECT_CONTEXT.md`。
- 修订发现反复的风格问题时，建议更新 `writing_style.md` 或 academic-writing-style-control 技能。

## 不要做

- 未要求不要继续扩写。
- 不要不声明就把论证改成另一条 storyline。
- 不要为修辞强化薄弱证据。
- 不要悄悄改关键术语。
- 不要只改语法而忽略论证和证据边界。

## 停止条件与交接

一次 fresh-context revision 结束应满足：已区分语言/结构/论证/证据问题；已说明是否偏离 `BLUEPRINT.md`；已完成指定范围的诊断或改写；已列出需回到数据/变量/文献/蓝图确认的问题；没有把结构性问题伪装成普通润色。

交接给最终检查（skill `final-checker`）：修订后草稿位置、未解决问题、是否需更新 `BLUEPRINT.md` 或 `PROJECT_CONTEXT.md`、最终检查重点关注的表图/变量/引用/贡献边界。

## 收尾报告

fresh-context revision 后，报告：

1. 审了什么；
2. 主导问题类型；
3. 草稿是否照蓝图；
4. claim 是否与证据对齐；
5. 改了什么；
6. 还有什么需人工判断；
7. 是否该更新任何项目文件。
