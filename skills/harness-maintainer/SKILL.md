---
name: harness-maintainer
stage: 项目与维护
trigger: 维护或修改 Research Harness 本身
description: Maintain and revise the user's personal social science Research Harness. Use when auditing, compressing, restructuring, or editing files under research_harness, including README, RESEARCH_PROFILE, shared_rules, workflows, templates, skills, agent_entries, FILE_MAP, TREE, and harness revision guides. Also use when checking instruction hierarchy, file detail level, language style, tool-neutral task routing, or whether harness rules are overengineered, redundant, stale, or inconsistent.
---

# harness-maintainer

## 用途

维护 Research Harness 本身，而不是在 harness 里跑某个研究项目。目标是让 harness 保持有用、轻量、内部一致、以社科论文生产为中心。

流程：先诊断，再提出有针对性的修改，用户同意或明确要求后做小范围、可审查的改动。

## 先读文件

改 harness 文件前，先读：

```text
research_harness/HARNESS_ENVIRONMENT_FILE_REVISION_GUIDE.md
research_harness/README.md
research_harness/RESEARCH_PROFILE.md
research_harness/FILE_MAP.md
research_harness/TREE.txt
```

再只读相关文件组：

```text
research_harness/shared_rules/
research_harness/workflows/
research_harness/templates/
research_harness/skills/
research_harness/agent_entries/
```

任务涉及 agent 指令模板、skill 结构、规则归属、文件篇幅或语言风格时，读 `references/template-patterns.md`。

## 不可动摇的本地原则

- harness 以社科论文生产为中心，不以某个 AI 工具为中心。
- 项目层默认保持轻量：`PROJECT_CONTEXT.md`、`VARIABLES.md`、`OUTPUT_SPEC.md`、`analysis_notes/INDEX.md`。
- `BLUEPRINT.md` 只在项目进入写作或蓝图阶段才建。
- 写作阶段，论文结构、段落功能、写作顺序和证据挂钩，`BLUEPRINT.md` 优先于 `PROJECT_CONTEXT.md`。
- 分析历史存 `analysis_notes/`，不要把历史塞进当前上下文。
- 不要恢复已放弃的默认：`STATE.md`、`DECISIONS.md`、`STORYLINE.md`、单设的“测量与方法文献”、过宽的文献矩阵字段、段落目标字数、强制段落对应表图。
- 保留外部 raw data 假设：大型公开调查数据常在 `/Users/wenbohu/课程资料/数据`。

## 文件归属测试

改任何一段前，先归类：

| 内容类型 | 最佳位置 |
| --- | --- |
| 跨项目稳定原则 | `shared_rules/` |
| 阶段流程与交接 | `workflows/` |
| 产物骨架或占位 | `templates/` |
| 可重复的操作流程 | `skills/*/SKILL.md` |
| 工具入口路由 | `agent_entries/` 或项目 `AGENTS.md`/`CLAUDE.md` |
| 当前项目事实 | 项目 `harness/PROJECT_CONTEXT.md` |
| 历史分析 | 项目 `analysis_notes/` |

一段内容同时适合多处时，留一个权威来源，其它指向它。

## 维护流程

1. 把请求映射到受影响的文件组。任务窄时不要读或重写整个 harness。
2. 改之前用 `grep`（或 `rg`）搜陈旧或冲突表述，也可直接跑 `scripts/check_harness.sh`。典型模式：`STATE.md`、`DECISIONS.md`、`STORYLINE.md`、`目标字数`、`测量与方法文献`、`对应表图`、`data/raw`、工具绑定的任务分工。
3. 按类型诊断：结构、不一致、冗余、过度细化、放错文件、措辞。
4. 改文件前用 3-6 条 bullet 说明计划改动。
5. 用小补丁。优先删除、合并、理清路由，而非大改写。
6. 增删或重命名文件时更新索引 `README.md`、`FILE_MAP.md`、`TREE.txt`；TREE 和 FILE_MAP 路由可用 `scripts/gen_tree.sh`、`scripts/gen_filemap_router.sh` 重生成。
7. 用 `grep`、`wc -l` 和文件预览做针对性验证。
8. 报告改了哪些文件、为什么、还有什么风险。

## 篇幅标准

软目标，不是硬规则：

| 文件类型 | 目标篇幅 |
| --- | --- |
| `README.md` | 人读的总览和安装地图；含目录树时通常 200-350 行 |
| `FILE_MAP.md` | 一行式说明；通常 100 行内 |
| `TREE.txt` | 只放文件树，无解释 |
| `RESEARCH_PROFILE.md` | 只放稳定偏好，无当前项目历史 |
| `shared_rules/*.md` | 每主题 50-120 行；无长示例或流程 |
| `workflows/*.md` | 80-180 行；适用场景、先读、输入、输出、停止条件、交接 |
| `templates/*.md` | 40-140 行；占位和结构，不写成填好的案例 |
| `skills/*/SKILL.md` | 80-220 行；具体流程和检查；长示例移到 `references/` |
| `agent_entries/global/*.md` | 80-120 行；只放路由和优先级 |
| 项目 agent 模板 | 40-80 行；只放本地读取顺序和覆盖 |
| 修订指南或 reference | 可更长，但加清晰标题，且不进自动加载的入口 |

文件超目标时，先看它是否在做另一类文件的活。

## 语言与写作风格

遵循 `HARNESS_ENVIRONMENT_FILE_REVISION_GUIDE.md` 的 §四.3“AI 友好写作规范”：中文主语言 + 英文受控词、祈使、可检查、bullet 化、每文件一个主语言、格式关键处给正反例。

## 本技能的输出格式

报告 harness 维护工作时用：

```text
诊断：
- ...

修改：
- file: reason

验证：
- command or check

后续：
- ...
```

除非用户要完整审计，最终报告保持简短。
