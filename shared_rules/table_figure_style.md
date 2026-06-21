# table_figure_style.md

## 文件定位

规定社科论文项目的表格、回归表、图形和 draft 输出风格。只保留跨项目稳定原则；具体期刊格式和项目特殊要求以 `Project/harness/OUTPUT_SPEC.md` 为准。

核心：输出接近正式社科论文 draft，不是网页、商业报告、教学讲义或软件演示。表图服务论证，不展示格式能力。

## 总体风格

- 默认简洁、克制、学术化。
- 不要：蓝色标题、彩色表头、大面积底色、过度加粗、复杂边框、阴影、渐变、装饰元素。
- 不要：网页仪表盘、卡片式排版、presentation deck 观感。
- 默认目标是论文 draft；要 presentation 风格需用户明确要求。

## 表格

- 优先三线表：顶线、表头下横线、底线为主，避免完整网格线。
- 数字对齐；变量名清楚；列标题简洁。
- 描述统计表按需含：变量标签、样本量、均值或比例、标准差或分布信息。
- 用可读变量标签，不直接用难懂的原始变量名（除非原始名已很清楚）。
- 表太长就拆：正文表只放支持主线的信息；完整模型、额外描述统计、稳健性进附录表。

## 回归表

- 向社会学/人口学/家庭期刊的常见格式看齐：模型编号、因变量说明、核心自变量、控制变量、标准误、显著性标记、样本量、必要模型统计量。
- 必须标注括号里是什么：标准误 / robust SE / clustered SE / 置信区间 / t / z。别让读者猜。
- 用了 robust、clustered、survey weights、固定效应、年份/队列效应、样本限制，在表注说明。
- 控制变量可全列，或正文主表压成 `Controls: Yes`（压缩时附录给完整表）。
- 不要把 Stata 原始回归输出当论文表粘贴；生成可进 draft 的版本 + 表题 + 表注。

## 图形

- 每张图有明确目的：核心描述性模式、模型预测值、异质性、组间差异、趋势或机制线索。不要为“有图”而画。
- 坐标轴清楚、图例简洁、标题准确。默认不用高饱和度颜色、复杂背景、阴影、3D、过度装饰。
- 已启用 `cleanplots` 或已有 ggplot theme 时沿用；可调标题、轴标签、图例位置、置信区间、导出格式，不重写大量美化参数。
- 正文图优先：边际效应、预测概率、组间差异、关键趋势。系数图要变量顺序有理论逻辑、标签清楚、置信区间可读；margins 图说明预测值的计算条件。
- 每张图配可进论文的 caption：展示什么、数据来源、样本限制，必要时说明控制了哪些变量。

## Exploratory 与 final

- 探索性 → `table/exploratory/`、`figure/exploratory/`。
- 确认可进正文或附录的 → `table/final/`、`figure/final/`。
- 未确认不要把探索性当 final；要覆盖 final 必须说明。

## 文档输出

- Word / Markdown / HTML 默认接近论文 draft。不要蓝色标题、花哨分隔线、彩色信息框、卡片布局、网页风格。
- 生成 HTML 时区分“学术分享版”和“论文 draft 版”；未明确要求不用醒目颜色、图标、复杂 CSS。

## 文件命名

- “类型 + 简短主题 + 必要版本”；文件名不替代表题、caption 或 memo。
- 好例：

```text
fig_gender.pdf
fig_future_uncertainty.pdf
fig_margins_main.pdf
tab_desc.docx
tab_main_models.xlsx
tab_robustness.docx
```

- 探索性可带 round 或日期：`fig_r01_gender.pdf`；final 用稳定名：`fig_main_effect.pdf`。
- 坏例：

```text
final_final.docx
new_new.xlsx
graph_test2.png
```

## 表图与正文

- 表图嵌入论证：生成时说明它服务哪个研究问题、假设、结果解释或 storyline。
- 正文引用先讲发现、再引表图作证据，不要只写“见表 1”。

## 任务结束汇报

每次生成表格、回归表、图形或 draft 文档后，说明：文件位置、exploratory/final、是否符合本规则和 `OUTPUT_SPEC.md`、是否需更新 `OUTPUT_SPEC.md` 或 `PROJECT_CONTEXT.md`。
