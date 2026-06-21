# code_style.md

## 文件定位

规定社科研究项目的代码风格、数据调用、输出路径和执行纪律。只保留跨项目稳定原则。

具体 Stata 写法、路径模板、log 文件名、表图导出和 analysis memo 格式，主要参考：

```text
skills/stata-socialscience-analysis/SKILL.md
workflows/data_exploration.md
templates/analysis_memo_template.md
Project/harness/OUTPUT_SPEC.md
```

## 核心原则

- 首要目标：可理解、可复现、可检查。代码帮研究者看清变量、样本、模型和结果，不是展示技术复杂性。
- 主分析代码线性、透明、可逐步检查；生产型代码可自动化，但与主分析分开，并说明输入、输出、是否覆盖旧结果。

## 数据调用

- 大型公开调查数据常在中央数据仓库：`/Users/wenbohu/课程资料/数据`。
- 项目 `data/` 放分析数据、派生数据、临时数据、变量字典和处理说明，不默认放完整 raw data。
- 可读取中央仓库的 source data，但不得修改、覆盖、移动或清理原始文件。写入只发生在项目目录内，除非用户指定其他位置。
- 代码中区分四类：

```text
source data      # 中央数据仓库中的原始数据，只读
derived data     # 由代码生成的项目分析数据
temporary data   # 运行过程中生成的临时文件
output files     # 表格、图形、模型结果、草稿和 memo
```

## 路径管理

- 路径集中、清楚、可改；不要在脚本里散落绝对路径。
- 必须用绝对路径时，集中放在 `00_setup.do` 或脚本开头，并标明对应 source data、project root、derived data、table 还是 figure output。
- 项目已有清楚路径结构时，优先遵守。

## 分析代码与生产代码

- 主分析代码（清洗、变量构造、描述统计、主模型、稳健性）：直观为先，不为省几行就用难懂的循环、嵌套宏或程序化写法。
- 生产型代码（批量画图/制表/导模型、appendix、bootstrap、simulation）：可用循环、宏、自动化，但放专门脚本，并说明循环对象、关键参数、输出路径、预期文件。

## Stata 与 R

- 主语言 Stata；R 用于 Stata 不便的数据整理、补充分析或 ggplot2 出版级图形。
- 无论哪种语言，变量命名、样本限制、输出路径、项目文件结构保持一致；Stata 与 R 之间用标准格式交接，存进项目目录。

## 表图代码

- 图形、制表、模型估计分块或分脚本；不要把估计、margins、绘图、导表压成一段难检查的代码。
- 表图输出遵守 `shared_rules/table_figure_style.md` 和项目 `OUTPUT_SPEC.md`；不声明不覆盖 final 输出。

## Log 与 memo

- 默认不随意建 log。log 只在正式跑完整流程、记录批量模型、调试复杂错误或保存复现记录时建。
- 所有 log 进项目指定 logs 目录，如 `code/logs/`；不要在项目根、data、draft、figure、table 生成零散 log。
- 每轮重要分析后生成 analysis memo 并更新 `analysis_notes/INDEX.md`；历史进 `analysis_notes/`，只有当前仍有约束力的结论和警示进 `PROJECT_CONTEXT.md`。

## 任务结束汇报

每次改代码或生成输出后，说明：文件变化、输出位置、是否覆盖旧文件、结果是否稳定、是否需更新 `PROJECT_CONTEXT.md`、`VARIABLES.md`、`OUTPUT_SPEC.md` 或 `analysis_notes/INDEX.md`。

不要只说“完成了”。输出必须可追踪、可复核、可继续迭代。
