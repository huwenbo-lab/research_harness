# literature_mapping.md

## 适用场景

用于文献定位和文献矩阵构建阶段。适合数据探索已经产生初步结果，研究者已有一个或多个可能 storyline，但尚未明确论文要进入哪一组学术对话的项目。

目标不是尽可能多地找到“相关文献”，而是把经验发现放入可写作、可发表、可对话的文献结构中。

## 先读文件

先读全局规则：

```text
RESEARCH_PROFILE.md
shared_rules/workflow_principles.md
shared_rules/literature_taxonomy.md
shared_rules/writing_style.md
```

再读项目文件：

```text
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/analysis_notes/INDEX.md
```

按需读取：

```text
Project/analysis_notes/round_memos/
Project/table/exploratory/
Project/figure/exploratory/
Project/table/final/
Project/figure/final/
Project/literature/matrix/
Project/literature/synthesis/
Project/literature/core_literature/
```

不要默认读取所有 round memos。先根据 `analysis_notes/INDEX.md` 判断哪些 memo 与当前文献问题相关。

## 输入

文献定位需要明确：

- 当前研究问题；
- 关键经验发现；
- 可能机制或 competing explanations；
- 目标人群、制度语境、数据类型和主要变量；
- 当前想进入或避开的文献对话；
- 本地文献库是否只有标题和摘要。

若 `PROJECT_CONTEXT.md` 已过时，应先更新当前研究问题、关键发现和初步 storyline，再开始大规模检索。

## 判断边界

如果文献库只能访问标题和摘要，AI 不能声称已经掌握文章完整论证、模型设定、稳健性检验和全部发现。

摘要层级检索适合：

- 定位文章属于哪条文献脉络；
- 判断文章可能与论文哪一部分相关；
- 筛选值得阅读全文的核心文献；
- 形成初步文献地图。

它不适合替代全文级理论重构、方法评价或结果比对。

## 步骤

1. 确认经验发现和初步 storyline。文献检索必须服务当前数据结果，不做脱离项目的主题检索。
2. 生成检索维度。至少区分因变量、核心机制、样本或语境、理论概念和竞争解释维度。
3. 初筛文献。基于标题和摘要识别候选文献，并按 `literature_taxonomy.md` 分类。
4. 生成文献矩阵。字段保持简洁，使用统一字段名。
5. 生成 synthesis memo。按研究脉络组织，不逐篇罗列。
6. 形成核心阅读清单。核心文献初步控制在 10-20 篇，并标记需要阅读全文的文献。
7. 判断是否启动 snowballing。只围绕少量候选核心文献追踪参考文献和被引文献。

## 文献矩阵字段

统一使用：

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

`literature_role` 使用：

```text
core_conversation
theoretical_anchor
empirical_precedent
institutional_background
competing_explanation
uncertain
```

测量、变量构造或方法用途写入 `project_relevance` 或 `notes`，不默认单列为文献大类。

## 输出

建议输出：

```text
Project/literature/matrix/literature_matrix.xlsx
Project/literature/synthesis/literature_synthesis.md
Project/literature/core_literature/core_set.md
```

可选输出：

```text
Project/literature/background_literature/background_set.md
Project/literature/snowballing/snowball_candidates.xlsx
Project/literature/snowballing/snowball_memo.md
```

若矩阵主要基于标题和摘要，应在输出中明确说明。

## 停止条件

可以进入 storyline 阶段的条件：

- 已识别本文可能进入的核心文献对话；
- 文献矩阵能说明主要文献与项目的关系；
- synthesis memo 能概括主要文献脉络；
- 核心阅读清单已经形成；
- 主要竞争解释已初步识别；
- 已标记哪些文献必须阅读全文。

## 交接

交给 storyline 阶段（skill `storyline-builder`）时，应提供：

- 文献对话候选；
- 核心文献和必须阅读全文清单；
- 理论锚点；
- 经验先例；
- 制度背景；
- 竞争解释；
- 当前经验发现与文献缺口的连接方式。
