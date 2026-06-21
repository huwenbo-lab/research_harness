# data_exploration.md

## 适用场景

用于数据探索、问题打磨与模型迭代阶段。适合你已带着数据和一个大概的研究问题进场、但尚未确定尖锐问题、主结果和核心表图的项目。

本阶段分两挡，心态和产出都不同：

- **探索挡**：边探索数据边把"大概的问题"磨成尖问题——针对谁、什么机制、与谁对话、缺口在哪。允许多试多画，产出放 `exploratory/`。
- **主分析 + 稳健挡**：锁定要写进论文的主结果，再用换样本、换设定、加控制变量、关键子群等稳健性/异质性检验反复捶它，确保扛得住审稿。产出放 `final/`。

数据探索不是机械找显著性，而是同时收敛"问题"和"主结果"。

## 先读文件

先读全局规则：

```text
RESEARCH_PROFILE.md
shared_rules/workflow_principles.md
shared_rules/code_style.md
shared_rules/table_figure_style.md
```

再读项目文件：

```text
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/harness/OUTPUT_SPEC.md
Project/analysis_notes/INDEX.md
```

不要默认读取所有历史 memo。先读 `analysis_notes/INDEX.md`，再按需读取相关 memo。若变量说明不完整，优先补 `VARIABLES.md`，不要凭空猜变量含义。

## 输入

- 进场时的大概研究问题；
- source data 位置，通常可能在 `/Users/wenbohu/课程资料/数据`；
- 项目 derived data 和输出目录；
- 样本范围、年份、权重、ID、实验分组或追踪结构；
- 当前最关心的因变量、核心解释变量和控制变量。

AI 可以读取中央数据仓库中的 source data，但不得修改、覆盖或移动原始数据。所有写入只发生在项目目录或用户明确指定的输出目录。

## 步骤

### 探索挡

1. 确认项目与数据。读 `PROJECT_CONTEXT.md` 和 `VARIABLES.md`，确认大概问题、数据来源、样本范围、核心变量和当前疑问。
2. 检查变量与样本。核查缺失、分布、类别比例、取值范围、异常值、编码方向、权重、ID 和样本限制。
3. 探索性分析。用描述统计、交叉表、均值差异、趋势图和初步模型找候选规律；放 `exploratory/`，乱一点无妨。
4. **磨尖研究问题**。对照候选发现、数据可行性和初步文献缺口，把"大概的问题"收紧成尖问题，更新 `PROJECT_CONTEXT.md` 的"研究问题"。问题磨尖是本挡的硬产出，不能跳过。

### 主分析 + 稳健挡

5. 锁定主结果。选定回答尖问题的主模型，说明模型选择理由（与因变量类型、数据结构、研究问题匹配）。
6. 稳健性与异质性。换样本、换设定、加/减控制变量、关键子群与替代测量，检验主结果是否扛得住；不稳的如实记入失败尝试。主结果产出放 `final/`。
7. 解释与判断。区分稳定结果、不稳定结果、描述性发现、潜在机制和过度解释；对每个主结果写清“能主张 / 不能主张（过度解释红线）”，记入 analysis memo 和 `PROJECT_CONTEXT.md`。

### 收尾

8. 记录本轮分析。生成 analysis memo，更新 `analysis_notes/INDEX.md`。
9. 判断是否更新项目上下文。研究问题（是否更尖）、关键发现、storyline 或下一步变化时，更新 `PROJECT_CONTEXT.md`。

## 输出

常见输出：

```text
Project/code/
Project/data/derived/
Project/table/exploratory/      # 探索挡
Project/figure/exploratory/     # 探索挡
Project/analysis_notes/round_memos/
Project/analysis_notes/INDEX.md
```

锁定并经确认的主结果输出进入：

```text
Project/table/final/            # 主分析+稳健挡
Project/figure/final/
```

此外，本阶段必须产出一个**磨尖的研究问题**（写入 `PROJECT_CONTEXT.md`）。Analysis memo 结构由 `templates/analysis_memo_template.md` 维护，不在本 workflow 复制完整模板。

## 失败尝试记录

失败尝试必须记录。失败包括代码报错、模型不稳定、变量含义不合适、样本量不足、结果不支持主线、图表无法解释、控制变量引入后主结果消失、交互项无理论解释等。

每个重要失败尝试至少说明：尝试了什么；为什么尝试；结果如何；为什么不采用；以后是否需要避免；何种条件下可以重新考虑。

若某个失败尝试对后续有强约束力，从 memo 提炼到 `PROJECT_CONTEXT.md` 的注意事项。

## 停止条件

可以进入文献定位或 storyline 阶段的条件：

- 研究问题已磨尖（针对谁、什么机制、与谁对话、缺口在哪），不再是进场时的泛泛方向；
- 核心因变量和样本范围基本确定；
- 至少有一组稳定经验发现，且主结果已过至少一组稳健性检验；
- 主要失败路径已记录；
- 研究者能说出当前最可能的 1-3 条 storyline；
- 下一步文献检索方向已明确。

## 交接

交给 `literature_mapping.md` 时，应提供：

- 磨尖的研究问题；
- 稳定经验发现与锁定的主结果；
- 关键变量与样本说明；
- 可能机制；
- 主结果表图与稳健性证据；
- 已知失败路径和不能过度主张的边界。
