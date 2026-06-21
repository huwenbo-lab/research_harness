# workflow_principles.md

## 文件定位

本文件规定 Research Harness 的工作流关系、上下文优先级、文件更新边界和维护原则。它不是某一阶段的操作手册；具体任务应进入对应 `workflows/` 或 `skills/`。

本文件适用于 Claude Code、Codex、ChatGPT 和其他本地 agent。工具名称不决定研究分工；当前任务模式决定应读取的 workflow 和 skill。

## 总体原则

这套 harness 以社会科学论文生产流程为中心。AI 的任务是帮助研究者把数据、文献、论证和写作组织得更清楚、更可复现，而不是替研究者决定研究问题、理论解释和最终论文主张。

工作流不是流水线。数据结果可能迫使文献重查；文献阅读可能改变 storyline；blueprint 共创可能暴露证据不足；fresh-context revision 也可能要求回到结果解释或结构设计。每次回退都应留下清楚的文件记录。

## 宏观阶段与承担者

研究流水线阶段（投稿前）：数据探索（探索 / 主分析+稳健两挡）→ 文献定位 → storyline 与 blueprint 共创 → 照蓝图成文 → fresh-context 修订与最终检查；投稿后：审稿回应（R&R）。

阶段顺序、各阶段读什么 / 产出什么 / 交接给谁、由哪个 workflow 或 skill 承担，见 `workflows/PIPELINE.md`（流水线总图，唯一来源）。本文件只负责上下文优先级、文件更新规则和任务模式。

## 项目层核心文件

项目层默认核心文件只有：

```text
harness/PROJECT_CONTEXT.md
harness/VARIABLES.md
harness/OUTPUT_SPEC.md
analysis_notes/INDEX.md
```

进入写作蓝图阶段后，再创建：

```text
draft/outline/BLUEPRINT.md
```

不要默认创建 `STATE.md`、`DECISIONS.md`、`STORYLINE.md` 或一组空的阶段文件。需要临时记录时，优先放入 `analysis_notes/` 并由 `INDEX.md` 索引。

## 上下文优先级

1. 用户当前明确指令优先。
2. 项目本地文件优先于全局 harness。
3. `PROJECT_CONTEXT.md` 负责当前研究问题、关键发现、storyline 和下一步任务。
4. `VARIABLES.md` 负责变量定义、编码、缺失处理、样本范围和模型用途。
5. `OUTPUT_SPEC.md` 负责表格、图形、文件命名、draft 输出和期刊格式要求。
6. `analysis_notes/` 保存历史过程；agent 默认先读 `analysis_notes/INDEX.md`，再按需读取具体 memo。
7. 写作阶段中，`BLUEPRINT.md` 对论文结构、段落功能、写作顺序和证据挂钩优先。

`BLUEPRINT.md` 不能覆盖数据事实、变量定义、样本范围、模型设定和输出格式。涉及这些内容时，应回到 `VARIABLES.md`、analysis memo、代码和结果文件。

## 何时更新文件

- 研究问题、关键发现、当前 storyline 或下一步任务变化时，更新 `PROJECT_CONTEXT.md`。
- 变量定义、编码、样本范围、缺失处理或模型用途变化时，更新 `VARIABLES.md`。
- 表格、图形、文件命名、期刊格式或 draft 输出要求变化时，更新 `OUTPUT_SPEC.md`。
- 完成重要分析、失败尝试、模型选择或结果解释时，写入 `analysis_notes/` 并更新 `analysis_notes/INDEX.md`。
- 进入正式写作前，生成或更新 `draft/outline/BLUEPRINT.md`。
- 反复出现跨项目问题时，更新全局 `shared_rules/` 或对应 skill。

## 任务模式

根据当前任务选择模式：

```text
exploratory analysis mode
confirmatory + robustness mode
literature mapping mode
storyline building mode
blueprint co-creation mode
blueprint execution mode
fresh-context editor mode
final checker mode
r_and_r mode
```

Claude Code 和 Codex 都可以承担讨论和执行任务。Codex 参与 storyline 时应关注变量、模型和可实现性；Claude Code 执行代码任务时也必须遵守代码和文件纪律。

## workflow 与 skill 的关系

Workflow 说明阶段如何推进。Skill 说明某类任务如何执行。

如果二者有重叠，以 workflow 决定阶段目标，以 skill 决定执行细节。不要把长步骤复制到 shared rule；不要把项目事实写进 skill。

## 维护原则

Harness 的目标是减少重复解释和降低混乱，不是制造新的维护负担。只有反复发生、跨项目有用、且能降低未来成本的规则，才沉淀为 shared rule、workflow、template 或 skill。

判断 workflow 是否有用，应看它是否帮助研究者更清楚地回答：数据说明了什么，文献允许如何解释，论文可以合理主张什么，哪些结论属于过度解释。
