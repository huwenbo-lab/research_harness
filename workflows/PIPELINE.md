# PIPELINE.md — 研究流水线总图

## 用途

这张图说明研究流水线各阶段的顺序、每个阶段读什么 / 产出什么 / 交接给谁、由哪个 workflow 或 skill 承担。覆盖从"带着数据和大概问题进场"到投稿、再到投稿后审稿回应的全过程。上下文优先级、文件更新规则和任务模式见 `shared_rules/workflow_principles.md`。

工作流不是单向流水线：数据可能逼着重查文献，文献可能改写 storyline，blueprint 共创可能暴露证据不足，修订可能要求回到结果，审稿回应可能要求补分析。每次回退都应留下文件记录。

尤其**前三段（探索 / 问题打磨 → 文献定位 → storyline）通常来回打圈**：你常带着数据和大概问题进场，问题在数据探索与文献阅读中逐步磨尖，而不是一次走直线。

## 阶段 → 任务模式 → 承担者 → 核心产出

| 宏观阶段 | 任务模式 | 承担文件 | 核心产出 |
| --- | --- | --- | --- |
| 一① 探索性分析 | exploratory | `workflows/data_exploration.md` ＋ skills `stata-socialscience-analysis`、`questionnaire-to-variables`、`analysis-memo-maintainer` | 候选发现、**磨尖的研究问题**、analysis memo |
| 一② 主分析 + 稳健性 | confirmatory + robustness | `workflows/data_exploration.md` ＋ skills `stata-socialscience-analysis`、`sociology-table-output` | 锁定的主结果、稳健性/异质性证据、final 表图 |
| 二 文献定位 | literature mapping | `workflows/literature_mapping.md` ＋ skills `literature-map-builder`、`citation-snowballing` | 文献矩阵、synthesis、核心阅读清单 |
| 三 storyline | storyline building | skill `storyline-builder` | 更新后的 `PROJECT_CONTEXT.md` |
| 三 blueprint | blueprint co-creation | skill `blueprint-builder` ＋ template `BLUEPRINT_template.md` | `BLUEPRINT.md` |
| 四 照蓝图成文 | drafting | `workflows/drafting.md` ＋ skills `sociology-table-output`、`academic-writing-style-control` | draft sections / full_draft、表图 |
| 五 fresh-context 修订 | fresh-context editor | skill `fresh-context-revision` | 诊断 / 改写后的草稿 |
| 五 最终检查 | final checker | skill `final-checker` | 分级审查报告 |
| 六 审稿回应（R&R） | revise & resubmit | `workflows/r_and_r.md` | response 信、补分析与修订稿 |

第一阶段含两挡：先**探索性**地找候选发现并把研究问题磨尖（放 `exploratory/`），再切到**主分析+稳健**锁定主结果、用稳健性检验扛住审稿（放 `final/`）。第六阶段（R&R）在投稿后发生，目前由 `workflows/r_and_r.md` ＋ `final-checker` / `fresh-context-revision` / 分析类 skill 组合完成，专门 skill 待建。

每个阶段的"先读文件 / 输入 / 停止条件"写在它的承担文件内（workflow 文件或对应 SKILL.md）。

## 阶段交接（谁接谁、带什么）

- **进场**：带着数据 + 一个大概的研究问题。
- **数据探索 → 文献定位**：磨尖的研究问题、稳定发现与锁定的主结果、关键变量与样本、可能机制、主结果表图与稳健性证据、已知失败路径与不可过度主张的边界。
- **文献定位 → storyline**：文献对话候选、核心文献与必读清单、理论锚点、经验先例、制度背景、竞争解释、经验发现与文献缺口的连接。
- **storyline → blueprint**：已选 storyline、核心发现、文献对话与核心文献、理论机制、主要证据、竞争解释、贡献边界、不应过度主张的内容。
- **blueprint → 成文**：已确认的 `BLUEPRINT.md`、必须遵守的主线与结构、必须使用的核心证据与文献、可适度发挥的段落、必须严格按证据写的段落、需避免的过度主张。
- **成文 → fresh-context 修订**：草稿位置、所用蓝图片段、偏离蓝图处及原因、未确认的表图/变量/文献/结果、希望重点检查的语言/结构/论证/证据问题。
- **修订 → 最终检查**：修订后草稿位置、未解决问题、是否需更新 `BLUEPRINT.md` 或 `PROJECT_CONTEXT.md`、最终检查重点关注的表图/变量/引用/贡献边界。
- **最终检查 → 投稿 → 审稿回应**：投稿后收到 decision，带审稿意见原文 + 现稿 + 数据/代码进入 R&R；需补分析的回"一② 主分析+稳健"，需改写的回"四 成文"/"五 修订"。

## 怎么用

- 按当前任务模式在上表找承担者：是 workflow 文件就读该 workflow；是 skill 就按 `FILE_MAP.md` 的"任务 → skill 路由"读对应 `SKILL.md`。
- 阶段可回退；回退后在 `analysis_notes/` 或对应项目文件留记录。
- 进入写作阶段后，论文结构、段落功能、写作顺序和证据挂钩以已确认的 `BLUEPRINT.md` 为准（见 `shared_rules/workflow_principles.md`）。
