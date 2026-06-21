---
name: final-checker
stage: 修订与检查
trigger: 投稿前或阶段性提交前综合检查
description: Use for a final or near-final review of a social science manuscript before submission, advisor/coauthor circulation, conference, or major revision — checking alignment across research question, literature, theory, data, models, results, tables/figures, structure, and style, and grading findings (must fix / recommended / minor / human judgment). Not proofreading-only.
---

# final-checker

## 用途

投稿、给导师/合作者传阅、会议报告或大改之前，对社科稿做最终或接近最终的审查时用。不是只校对文字，而是检查研究问题、文献对话、理论 claim、数据、方法、结果、表图和写作风格是否一致。

## 先读文件

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/writing_style.md
~/.research_harness/shared_rules/table_figure_style.md
~/.research_harness/workflows/PIPELINE.md
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/harness/OUTPUT_SPEC.md
Project/draft/outline/BLUEPRINT.md
Project/draft/full_draft/
Project/table/final/
Project/figure/final/
Project/literature/synthesis/literature_synthesis.md
Project/literature/matrix/literature_matrix.xlsx
```

需要核验证据时，查相关 analysis memo、代码和结果文件。

## 核心原则

不要把所有问题都当写作问题。区分：

```text
研究问题
文献对话
理论机制
数据与变量
模型与结果
表格与图形
结构
语言风格
证据边界
```

不要只润色文字。判断论文是否内部自洽、claim 是否站得住。

## 问题分级

把发现分四级：

```text
must fix
recommended revision
minor issue
human judgment needed
```

帮研究者决定投稿前哪些最要紧。

## 关键检查

- **研究问题**：问题是否清楚、具体、连到贡献？引言是否说清这篇论文为什么存在？
- **文献对话**：是否进入一场可识别的文献对话，而非罗列研究？核心文献在不在？若文献只基于标题摘要，claim 是否足够谨慎？
- **理论与机制**：机制是真测了还是只是推断？因果或机制 claim 是否与设计相称？
- **数据与变量**：数据来源、样本限制、变量构造、编码方向、缺失、权重、标准误是否说清？变量名在正文、表格和 `VARIABLES.md` 间是否一致？
- **模型与结果**：模型是否匹配因变量类型和数据结构？结果解释是否正确？稳健性是否有意义？正文与表格是否一致？
- **表格与图形**：最终输出是否遵循 `OUTPUT_SPEC.md`？表注是否完整？图是否可读？每张正文表图是否服务 storyline？
- **结构**：是否遵循 `BLUEPRINT.md`（或有理由的更新）？各节是否层层递进？讨论是否回到研究问题？
- **风格**：是否避开 AI 腔、空过渡、泛化的贡献 claim、抽象名词堆砌？

## 输出格式

```markdown
# 最终检查报告

## 总体判断

## 投稿/传阅前必须修

## 建议修订

## 小问题

## 需人工判断

## 研究问题与贡献

## 文献与理论

## 数据、变量与方法

## 结果与证据

## 表格与图形

## 结构与写作

## 建议更新的文件
```

## 不要做

- 不要默认全文重写。
- 不要把风格当成唯一问题。
- 不要不查表格或 memo 就默认草稿的经验 claim 成立。
- 不要把有限证据写成更强的 claim。
- 不要忽视正文、变量文件和表格之间的不一致。

## 停止条件

最终检查结束应明确：论文是否已有清楚研究问题；文献对话是否明确；变量和模型是否可复核；核心结果是否与正文一致；表图是否接近论文标准；结论是否存在过度外推；语言是否仍有明显 AI 痕迹；哪些问题仍需研究者人工判断。

## 收尾报告

最终检查后，报告：

1. 稿件就绪程度；
2. must-fix 问题；
3. 证据与 claim 是否对齐；
4. 表图是否达到 draft 标准；
5. 是否该更新项目上下文或蓝图；
6. 建议的下一步。
