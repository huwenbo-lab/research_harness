---
name: academic-writing-style-control
stage: 主线与写作产物
trigger: 中/英文学术写作风格控制、去 AI 腔
description: Use when revising academic writing style in Chinese or English for sociology/demography/family papers — removing AI-like prose, stabilizing concepts, tightening argument-evidence fit, and aligning with journal style. For clarity and de-AI-ification, not for making prose more ornate and not for full structural rewriting.
---

# academic-writing-style-control

## 用途

修订中文或英文学术写作风格时用，面向社会学、人口学、家庭、人口研究等社科论文。不是把文字写得更华丽，而是让它更清楚、更少 AI 腔、概念更稳、与证据更贴、更接近期刊风格。

## 先读文件

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/writing_style.md
Project/harness/PROJECT_CONTEXT.md
Project/draft/outline/BLUEPRINT.md
```

涉及结果解释时，再读：

```text
Project/harness/VARIABLES.md
Project/table/final/
Project/figure/final/
Project/analysis_notes/INDEX.md
```

不要在不清楚证据是否支撑的情况下改动经验 claim。

## 核心原则

风格修订要服务论证，不是把句子改顺。改顺的句子仍可能是错的、含糊的、过度主张的或概念不稳的。每次修订都问：

```text
这句有没有明确的 claim？
claim 是否来自证据？
是否贴合段落功能？
概念是否稳定？
是否避开了模板化 AI 表达？
```

## 中文学术风格

- 向《社会学研究》《社会》《社会学评论》看齐：问题意识清楚、概念稳定、论证紧而有节制、段落层层推进。
- 除非用户要这种体裁，不要改成政策报告、媒体评论或面向公众的总结。
- 减少这些常见毛病（重复或无支撑时多半是 AI 腔）：

```text
“随着社会的发展”
“近年来……日益受到关注”
“具有重要意义”
“值得注意的是”
“进一步而言”
“提供了新的视角”
“复杂而多元”
“深刻影响”
“从某种意义上说”
```

- 好的中文学术段落通常有：明确功能、一个中心 claim、概念纪律、证据或文献支撑、向下一部分的过渡。

## 英文学术风格

- 可参考 AJS、ASR、Demography、Social Forces、Population and Development Review、European Sociological Review。
- 避开模板化 AI 表达：

```text
plays a crucial role
sheds light on
fills an important gap
complex and multifaceted
important implications
in today's rapidly changing society
it is important to note that
not only ... but also ...
```

- 避免连接词堆砌：

```text
therefore
moreover
furthermore
in addition
overall
```

连接词不禁用，但不能替代真实的逻辑推进。优先具体主语和清晰动词，避免一长串抽象名词，不要把 claim 强化到超出证据。

## 概念一致

不要随意互换相关但不同的概念，例如：

```text
uncertainty
future expectations
planability
risk perception
pessimism
```

它们可能相关，但不自动等同。marriage intention、family formation、fertility intention、marriage value、gender ideology、relationship experience 同样要小心。草稿用了多个术语时，要么统一，要么说明它们的关系。

## 证据边界

- 风格修订不得把 claim 改得强过设计允许。设计是描述性、相关性、横截面或探索性时，避免强因果语言，除非有理由。
- 更弱也往往更合适的动词：

```text
is associated with
is linked to
corresponds to
is consistent with
suggests
points to
may reflect
```

`causes`、`drives`、`demonstrates`、`proves` 这类强动词需要更强的设计和证据。

## 修订模式

- **轻度风格控制**：论证已稳时用。提清晰、减重复、去明显 AI 腔。
- **段落级重构**：段落有想法但内部逻辑乱时用。围绕一个功能、一个中心 claim 重组。
- **论证边界修订**：写得过度主张时用。降因果语言、限定机制、让 claim 对齐证据。
- **fresh-context 风格审查**：改另一个 AI 或上一轮生成的草稿时用。重点找 AI 语言模式、概念漂移、段落空转。

## 输出格式

改短文本时，给：

```text
修订版
修订说明
仍存风险
```

审整节时，给：

```text
总体诊断
主要风格问题
主要论证问题
段落级建议
可选的修订段落
```

需要先诊断时，不要默认全文重写。

## 不要做

- 不要把文字写得更花哨。
- 不要逐词换同义词，那会造成概念漂移。
- 不要删掉所有有助清晰的结构标记。
- 不要把学术中文改成口语。
- 不要把精确英文改成泛泛的“打磨过”散文。
- 证据有限时，不要掩盖不确定性。

## 收尾报告

风格控制后，报告：

1. 主要问题是语言、结构、概念还是证据边界；
2. 是否下调了某些 claim；
3. 是否统一了术语；
4. 草稿是否仍需人工判断；
5. 是否该更新 `BLUEPRINT.md` 或 `PROJECT_CONTEXT.md`。
