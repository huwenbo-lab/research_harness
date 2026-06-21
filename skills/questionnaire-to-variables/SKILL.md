---
name: questionnaire-to-variables
stage: 数据与变量
trigger: 把问卷、codebook、题项整理成变量说明（VARIABLES.md）
description: Use when translating a questionnaire, survey instrument, codebook, or survey module into research-ready variable documentation — linking items to concepts, variable roles, coding, missing-data handling, and model or descriptive uses. Produces or updates VARIABLES.md.
---

# questionnaire-to-variables

## 用途

把问卷、调查工具、codebook 或问卷模块整理成研究可用的变量说明时用。面向“已有问卷和数据、需要 AI 把题项连到概念、变量角色、模型用途、描述用途以及保留/修改决定”的项目。

## 先读文件

```text
~/.research_harness/RESEARCH_PROFILE.md
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/harness/OUTPUT_SPEC.md
```

有问卷或 codebook 就直接用；只有部分题项文本时，说明限制。

## 核心原则

题项不只看措辞质量，要看研究用途。对每个题项或题组问：

```text
它测的是什么概念？
能否干净地操作化？
能担什么变量角色？
能进模型、指数、类型学、机制分析、调节分析，还是描述报告？
主要服务学术论文、公共报告、样本描述还是数据质量？
该保留、修改、合并还是删？
```

## 变量角色

用这些角色：

```text
dependent variable
core independent variable
mechanism variable
moderator / heterogeneity variable
control variable
descriptive variable
grouping variable
report-only indicator
data quality / screening variable
uncertain
```

不要把每个题项都硬塞进回归。有些题项主要用于报告、描述、样本刻画或附录。

## 写入 VARIABLES.md

更新或起草 `VARIABLES.md` 时，以变量为中心，而不是逐题复制。每个重要变量含：

```text
变量名
变量标签
概念含义
来源题项
编码 / 取值方向
缺失处理
变量角色
分析用途
注意事项
```

数据集变量名未知时，用临时名并标注为临时。

## 量表与指数构造

- 多题项构念，评估能否构成指数或量表；先看概念一致性，数据可得时再查信度。
- 记录：

```text
题项集
预期方向
是否需反向编码
可能的指数构造
是否同时保留单题
局限
```

- 不要声称一组题项构成“已验证量表”，除非基于已知量表或经过实证检验。

## 保留 / 修改 / 合并 / 删除建议

评估题项时用四类建议：

```text
keep
revise
merge
drop
```

每条建议都要有理由。可接受的理由：概念重要性、变量用途、与既往调查可比、理论相关、测量弱、冗余、应答负担、措辞不清、缺乏分析用途、与核心研究问题不匹配。

## 输出格式

模块级评估用：

```markdown
## 模块名

### 测量的核心概念

### 变量用途

### 适合建模的题项

### 适合报告/描述的题项

### 需修改的题项

### 需合并或删除的题项

### 对 VARIABLES.md 的建议更新
```

变量说明任务则产出可直接粘进 `VARIABLES.md` 的条目。

## 不要做

- 不要只润色措辞。
- 不要把每个题项当同等重要。
- 不要假设每个态度题都该成为回归变量。
- 项目需要重叠时，不要忽视与既往调查的可比性。
- 变量名未知时不要编造。
- 不要把直接的主观解释不加注意地当成严格因果机制。

## 收尾报告

任务后，报告：

1. 识别的概念；
2. 应进入分析的变量；
3. 主要用于报告或描述的变量；
4. 需修改、合并或删除的题项；
5. 对 `VARIABLES.md` 的建议更新；
6. 未解决的编码或问卷问题。
