---
name: sociology-table-output
stage: 主线与写作产物
trigger: 生成/评估表格、回归表、图形、caption（论文 draft 风格）
description: Use when generating, formatting, or evaluating tables, regression tables, figures, captions, and table notes for sociology/demography/family papers, so outputs look like a formal paper draft (three-line tables, complete notes, argument-driven figures) rather than a webpage, slide, dashboard, or raw software output. Not for general data visualization or non-academic reporting.
---

# sociology-table-output

## 用途

生成、修改、格式化或评估社科论文的表格、回归表、图形、caption 和表注时用。目标：输出像正式论文 draft，不像网页、PPT、dashboard 或软件控制台。

## 先读文件

```text
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/shared_rules/table_figure_style.md
~/.research_harness/shared_rules/code_style.md
Project/harness/OUTPUT_SPEC.md
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
```

文件缺失时，按下面原则做，并说明所做假设。

## 总原则

- 默认风格：学术、克制、面向论文 draft。
- 不要：网页风格、彩色标题、卡片布局、dashboard 排版、装饰元素、商业报告观感。
- 每张表图必须在论文里有明确功能：样本描述、描述性模式、主模型、机制、异质性、稳健性或附录证据。不要因为"能做"就做。

## 表格

- 尽量用三线表：顶线、表头线、底线。不要全网格线、彩色表头、蓝色标题、粗边框、过度加粗。
- 格式受限做不出真三线表时，用最少边框近似。
- 描述统计表含：清晰变量标签、样本量、均值或比例、标准差或分布信息、必要的分组。
- 有可读标签就不要暴露原始变量名；必须用原始名时加解释。

## 回归表

- 向社科期刊表看齐：模型编号、可读变量标签、标准误或置信区间、样本量、关键模型统计量。
- 必须注明括号里是什么：标准误 / robust SE / clustered SE / 置信区间 / t / z。
- 用了 robust、clustered、weighted、fixed-effects、survey 或 multilevel，在表注说明。
- 控制变量可全列，或按表长压成 `Controls: Yes`；主表压掉时，注明完整模型见附录表。
- 不要把 Stata 原始输出直接当论文表粘贴。

## 图形

- 干净、服务论证：描述性模式、预测概率、边际效应、组间差异、趋势、系数估计或机制证据。
- 用 Stata 且已启用 `cleanplots` 时，沿用当前默认 scheme；未要求不做大量自定义。专注 labels、轴标题、legend、置信区间、导出格式。
- 不要 3D、过多颜色、重背景、多余网格线、装饰性格式。颜色只在区分信息时用。

## 探索性 vs 最终输出

- 探索性 → `table/exploratory/`、`figure/exploratory/`。
- 最终候选 → `table/final/`、`figure/final/`。
- 未经确认不要把探索性当最终。最终输出要有可读文件名、标签、表注和 caption。

## 文件命名

- 简洁有信息：标明类型、主题、必要版本；不要塞完整模型设定。
- 复杂细节进 caption、表注或 analysis memo，不进文件名。

好例：

```text
fig_main_effect.pdf
fig_gender.pdf
tab_desc.docx
tab_main_models.xlsx
tab_robustness.docx
```

探索性：

```text
fig_r01_gender.pdf
tab_r02_models.xlsx
```

坏例：

```text
graph1.pdf
newtable.xlsx
final_final.docx
```

## Caption 与表注

- 每张最终候选表图都要有可用标题和注。caption 说明：展示了什么、数据来源、样本限制、必要的关键模型条件。
- 表注解释：标准误、显著性星号、固定效应、控制变量、权重、样本限制、缩写。
- 不要把 caption 写成泛泛标签；它应帮读者看懂这张表图如何支撑论文。

## Word / Markdown / HTML / Excel

- Word、Markdown：默认论文 draft 风格。不要彩色标题、蓝字、卡片、装饰分隔线、PPT 化排版。
- Excel：结构清晰、便于下游使用；可以不如 Word 精致，但 sheet 名、标签、注要清楚。
- HTML：先确认是论文 draft HTML 还是分享用可视化报告；未要求不要做成 dashboard。

## 与 storyline 的关系

- 出最终候选前，想清楚每张表图与论文 storyline 的关系；关系不清就说出来，并建议它该进探索性 notes、附录，还是删掉。
- Results 部分，表图是论证的证据，不是数字仓库。

## 收尾报告

输出或修改后，报告：

1. 建了哪些文件；
2. 存在哪里；
3. 是探索性还是最终候选；
4. 是否覆盖了已有文件；
5. 每张表图要展示什么；
6. 适合正文、附录还是 analysis notes；
7. 是否该更新 `OUTPUT_SPEC.md`、`PROJECT_CONTEXT.md` 或 `BLUEPRINT.md`。
