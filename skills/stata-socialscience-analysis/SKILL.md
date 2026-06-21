---
name: stata-socialscience-analysis
stage: 数据与变量
trigger: 写/改/审 Stata 或 R 分析代码、做分析、写 analysis memo
description: Use when writing, revising, reviewing, or explaining Stata (or R) code for social science data analysis — sociology, demography, family research, stratification, survey/panel/conjoint analysis — covering data cleaning, variable construction, models, figures, tables, logs, and analysis memos. Emphasizes readable, reproducible, theory-aware code and the source/derived/temp/output data distinction. Not for highly compressed, automation-only scripting.
---

# stata-socialscience-analysis

## 用途

写、改、审、讲 Stata（或 R）社科分析代码时用：社会学、人口学、家庭、分层、survey/panel/conjoint 等实证项目，涵盖清洗、变量构造、模型、图、表、log 和 analysis memo。目标是可读、可复现、有理论意识的代码，不是最短或全自动脚本。

## 先读文件

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/code_style.md
~/.research_harness/shared_rules/table_figure_style.md
~/.research_harness/workflows/data_exploration.md
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/harness/OUTPUT_SPEC.md
Project/analysis_notes/INDEX.md
```

文件缺失时，谨慎推断项目结构并说明假设。不要凭空编造变量含义、样本限制或数据位置。

## 核心原则

- 目标不是最短代码，而是研究者能读、能审、能改、能对上论文论证的代码。
- 区分两类代码，这是核心：
  - **主分析代码**（清洗、变量构造、描述统计、主模型、稳健性、关键样本限制）：线性、透明、可逐步检查。
  - **production 代码**（批量画图/制表、附录生成、重复 margins、跨多结果或子群的循环、bootstrap、模拟）：可用循环/macro/program，但复杂度必须隔离、有注释、放专门脚本。

## 数据管理

- 大型公开调查数据与长期数据资产常在中央数据仓库：`/Users/wenbohu/课程资料/数据`。
- 不要假设 raw data 在项目目录里。项目 `data/` 通常放派生数据、临时数据、字典或项目分析数据。
- 绝不修改、覆盖、移动或删除中央仓库的 source data。所有清洗、合并、筛样、变量构造都通过代码完成，结果存进项目目录。
- 始终区分四类：

```text
source data      # 原始数据，只读
derived data     # 代码生成的项目分析数据
temporary data   # 处理中的中间文件
output files     # 表、图、log、memo、draft
```

## 推荐代码结构

没有现成结构时，用或建议：

```text
code/
├── 00_setup.do
├── 01_clean.do
├── 02_descriptive.do
├── 03_models.do
├── 04_figures.do
├── 05_tables.do
├── _run_all.do
└── logs/
```

不要把脚本散落各处，不要建一堆名字不清的临时文件。

## 路径设置

路径集中在 `00_setup.do` 或脚本顶部，不要满文件重复绝对路径。示例：

```stata
global project    "/path/to/current/project"
global source     "/Users/wenbohu/课程资料/数据"
global derived    "$project/data/derived"
global temp       "$project/data/temp"
global tables     "$project/table"
global figures    "$project/figure"
global logs       "$project/code/logs"
```

按实际项目调整；项目已有清晰结构时不要硬套。

## Stata 风格

- 用可读、可检查的代码；直白写法更清楚时，不用嵌套 macro、晦涩循环或程序化结构。
- 只在循环能真正减少重复和出错时用；用循环时讲清循环对象、结果、子群、模型列表或文件输出模式。
- 变量构造在代码旁注释，解释概念和编码方向，不只是复述命令。
- 估计、margins、画图、导表通常分到不同代码块或脚本；不要一大块里又估模型又算 margins 又画图又导文件。

## Log 规则

- 默认不开 log。仅在有明确用途时开：整流程运行、批量模型输出、复杂报错调试、复现记录、大批表图生成。
- 所有 log 进 `code/logs/`（或其它明确指定的 logs 目录）。
- log 文件名有意义但简洁，如 `2026-06-01_03_models.log`、`r02_model_debug.log`。
- 未明确要求，不要在项目根、data、draft、table、figure 目录生成 log。
- 临时调试 log 标明是临时的；任务结束时说明该留还是删。

## 画图规则

- 用 Stata 且已启用 `cleanplots` 时，沿用当前 scheme；未要求不做大量美化。
- 图代码目标是正确呈现结果，不是重设计风格。可设 labels、标题、legend、置信区间、轴刻度、导出格式；避免复杂调色板、改背景、主题、装饰选项。
- 允许批量画图，但放专门脚本如 `04_figures.do`。

## 表格规则

- 不要把 Stata 原始输出当论文表粘贴。出表遵循项目 `OUTPUT_SPEC.md` 和全局表格规则。
- 探索性 → `table/exploratory/`、`figure/exploratory/`；最终候选 → `table/final/`、`figure/final/`。
- 不声明就不要覆盖最终输出。

## analysis memo 要求

- 每次重要分析迭代后，生成或建议生成 analysis memo。重要迭代包括：模型设定、样本限制、变量构造、核心图、主表、稳健性或与 storyline 相关的解释发生变化。
- memo 存 `analysis_notes/round_memos/`，并更新 `analysis_notes/INDEX.md`。
- memo 至少含：

```text
分析目的
使用的数据与样本
运行的模型或图
主要发现
失败尝试及放弃理由
对 storyline 的影响
生成的文件
下一步
是否需更新 PROJECT_CONTEXT.md
```

- 失败记录很重要：模型/变量/图不行时说明为什么，避免以后重复踩。

## 收尾报告

每个 Stata/数据任务结束都报告：

1. 改了哪些文件；
2. 建了哪些文件；
3. 读了什么数据、写了什么数据；
4. 生成了哪些表图；
5. 是否生成 log；
6. 是否覆盖了已有文件；
7. 主要经验结论；
8. 不稳或失败的结果；
9. 是否该更新 `PROJECT_CONTEXT.md`、`VARIABLES.md`、`OUTPUT_SPEC.md` 或 `analysis_notes/INDEX.md`。

不要只说“done”。
