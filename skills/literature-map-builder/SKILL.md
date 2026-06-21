---
name: literature-map-builder
stage: 文献
trigger: 从标题摘要库检索、分类、做文献矩阵与 synthesis
description: Use when searching, filtering, classifying, or synthesizing literature for a social science project from a local title-and-abstract database, building a function-based literature matrix and synthesis that serve the paper's storyline. Emphasizes cautious claims when only titles and abstracts are available. Not for reference/citation chasing once a core set exists (use citation-snowballing).
---

# literature-map-builder

## 用途

为社科项目检索、筛选、分类、综合文献时用，尤其是基于本地“标题+摘要”文献库。库里常没有全文，所以重在文章定位、相关性和论文功能分类，不对方法、结果、机制下过度自信的判断。

## 先读文件

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/literature_taxonomy.md
~/.research_harness/workflows/literature_mapping.md
Project/harness/PROJECT_CONTEXT.md
Project/analysis_notes/INDEX.md
Project/literature/
```

项目上下文缺失或过时时，先问或推断当前研究问题和关键经验发现再检索。文献定位跟着项目正在形成的 storyline 走，不做脱离项目的关键词检索。

## 核心原则

目标不是把“相关”文章最大化，而是找到能把论文放进某场学术对话的文章。对每篇问：

1. 它在论文里可能扮演什么角色？
2. 论文哪一部分可能用到它？
3. 标题/摘要够不够，还是要读全文？
4. 它支持当前 storyline、提供背景、给理论锚点、做经验先例，还是提出竞争解释？

## 文献库限制

- 只有标题和摘要时，不要声称掌握全文论证、模型设计、稳健性或细节发现，除非摘要或用户笔记里有。
- 用谨慎措辞：

```text
摘要显示……
这篇似乎与……相关
这可能用于……
作为核心 claim 前应核对全文。
```

- 不要写（除非有信息支撑）：

```text
该文证明……
作者通过稳健性检验表明……
这篇确定地确立了……
```

## 功能分类

按文章在论文里的可能功能分类，用这些类别：

```text
core_conversation
theoretical_anchor
empirical_precedent
institutional_background
competing_explanation
uncertain
```

不要默认单设“测量与方法”类。某篇主要用于测量、变量构造或方法选择时，记进 `project_relevance` 或 `notes`。

- **core_conversation**：论文必须直接对话的文章，通常共享研究问题、因变量、理论争论、经验对象或机制；缺了它们文献综述会显得不完整。
- **theoretical_anchor**：提供有用概念、机制或理论语言，即使经验对象不同。
- **empirical_precedent**：提供相似数据、样本、模型、结果或经验模式。
- **institutional_background**：提供社会、人口、制度、文化或政策背景。
- **competing_explanation**：提出替代解释、选择效应、反向因果、不同机制或相反发现。
- **uncertain**：可能相关但仅凭标题摘要无法确信分类。

## 文献矩阵字段

矩阵保持简单。建议字段：

```text
citation_key
authors_year
title
journal
year
abstract
literature_role
relevance_level
project_relevance
paper_section
must_read_full_text
notes
```

`citation_key` 在源库没有时可选。最重要的是 `project_relevance`，说明这篇在项目里可能怎么用。库里只有标题摘要时，不要拆成太多过细字段。`project_relevance` 示例：

```text
可用于把“未来不确定性”框定为家庭形成决策的机制。
研究城市青年婚姻意愿的潜在经验先例。
教育扩张与中国婚姻市场变化的背景来源。
可能的竞争解释：观察到的态度可能是选择而非价值变化。
与引言相关，但可能不是 core conversation。
```

## 相关性等级

用简单等级：

```text
high
medium
low
uncertain
```

`high` = 很可能是 core conversation 或必读理论锚点；`medium` = 有用但不核心；`low` = 背景或弱相关；`uncertain` = 摘要不足以判断。

## 输出文件

标准文献定位任务产出：

```text
Project/literature/matrix/literature_matrix.xlsx
Project/literature/synthesis/literature_synthesis.md
Project/literature/core_literature/core_set.md
```

可选：

```text
Project/literature/background_literature/background_set.md
Project/literature/snowballing/snowball_candidates.xlsx
Project/literature/snowballing/snowball_memo.md
```

只用了标题摘要时，在矩阵或 synthesis memo 里明确说明。

## 文献综合 memo

synthesis memo 不逐篇总结，而是把文献组织成几场研究对话。应回答：

1. 本项目能进入哪些对话？
2. 每场对话已经解释了什么？
3. 还有什么没解释清？
4. 用户的经验发现如何连接这些缺口？
5. 哪些文章可能是核心？
6. 哪些只是背景？
7. 哪些竞争解释要处理？
8. 哪些必须读全文？

## 核心文献筛选

- 核心文献要精选，初始核心集常 10–20 篇。不要因为共享关键词就把太多标为核心。
- 一篇能进核心集，应是它很可能塑造论文的 framing、理论、研究问题、解释或贡献表述。
- 只有标题摘要时，核心标记是临时的，待核全文。

## Snowballing

只在确定小核心集后才 snowball，不要追所有相关文章。用 snowballing 找：

```text
核心文章引用的经典来源
引用核心文章的近期论文
缺失的理论锚点
重要的竞争解释
高影响的经验先例
```

每个候选都要有纳入理由；不要因为它出现在参考文献里就加。详细追踪流程见 `citation-snowballing`。

## 收尾报告

文献定位任务后，报告：

1. 检索依据或关键词；
2. 筛了多少篇；
3. 保留多少篇；
4. 用的分类方案；
5. 核心文献候选；
6. 需读全文的文章；
7. 识别出的主要文献对话；
8. 是否该更新 `PROJECT_CONTEXT.md`；
9. 是否该修订当前 storyline。
