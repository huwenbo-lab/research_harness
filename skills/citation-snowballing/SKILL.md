---
name: citation-snowballing
stage: 文献
trigger: 已确定核心文献后做参考文献追踪和被引追踪
description: Use only after a provisional core literature set exists, to expand it through reference chasing and citation chasing — finding missing classics, recent extensions, competing explanations, or theoretical anchors within a bounded scope. Not for broad initial literature search (use literature-map-builder first).
---

# citation-snowballing

## 用途

围绕一小组核心文献，做参考文献追踪（reference chasing）和被引追踪（citation chasing）时用。不用于宽泛检索：只在项目已确定临时核心集、需要补缺失的经典、近期扩展、重要竞争解释或关键理论锚点时用。

## 先读文件

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/literature_taxonomy.md
~/.research_harness/workflows/literature_mapping.md
Project/harness/PROJECT_CONTEXT.md
Project/literature/core_literature/core_set.md
Project/literature/matrix/literature_matrix.xlsx
Project/literature/synthesis/literature_synthesis.md
```

没有核心集时不要开始 snowball，先用 `literature-map-builder`。

## 核心原则

- snowballing 是补文献地图的缺口，不是无限扩张文献。
- 只从小种子集出发，种子集通常 10–20 篇核心。不要 snowball 每篇相关文章。

## 何时用

```text
核心文献集已确定
某篇关键文章像是某场对话的锚
文献地图缺经典来源
项目需要引用某核心工作的近期论文
某个竞争解释覆盖不足
读完某核心文章想追它的参考文献
```

不要用本技能做初始文献发现。

## 输入限制

- 只有标题摘要时谨慎：不要声称掌握参考文献或引用网络，除非有全文、元数据、用户笔记或引文库支撑。
- 拿不到真实参考文献列表时，产出一个 snowballing 计划，而不是编造候选。

## 候选分类

每个候选按可能功能分类：

```text
classic_source
recent_extension
theoretical_anchor
empirical_precedent
institutional_background
competing_explanation
method_or_measurement_note
uncertain
```

与通用文献分类不同，`method_or_measurement_note` 这里可作为考虑某候选的狭义理由，但不必升为主文献大类。

## 输出字段

候选用简单结构：

```text
seed_paper
candidate_authors_year
candidate_title
candidate_source
candidate_type
reason_for_inclusion
likely_use_in_project
priority
must_read_full_text
notes
```

`reason_for_inclusion` 必填。不解释为什么重要，就不要纳入候选。

## 优先级

```text
high
medium
low
uncertain
```

`high` = 重要到值得读或加进核心矩阵；`medium` = 可能有用；`low` = 背景或可选；`uncertain` = 信息不足。

## snowballing memo

除候选矩阵外，生成 memo 说明：

1. 用了哪些种子文章；
2. 为什么选这些种子；
3. 找到哪些类型的缺失文献；
4. 哪些候选应加进核心集；
5. 哪些只是背景；
6. 哪些需核全文；
7. 是否该更新当前 storyline 或文献综合。

## 输出文件

```text
Project/literature/snowballing/snowball_candidates.xlsx
Project/literature/snowballing/snowball_memo.md
```

确认的候选之后可并入：

```text
Project/literature/matrix/literature_matrix.xlsx
Project/literature/core_literature/core_set.md
```

未经用户确认，不要自动并入核心集。

## 不要做

- 不要 snowball 所有相关文章。
- 不要只因为出现在参考文献里就加。
- 不要编造参考文献内容。
- 不要把只有标题的候选当成已完全理解。
- 不要把 snowballing 做成一轮新的宽泛文献综述。

## 收尾报告

snowballing 后，报告：

1. 用的种子文章；
2. 识别出多少候选；
3. 高优先候选；
4. 需读全文的候选；
5. 建议加入核心文献集的；
6. 是否该更新文献综合或项目 storyline。
