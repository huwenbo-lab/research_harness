---
name: project-harness-initializer
stage: 项目与维护
trigger: 初始化或改造项目级轻量 harness
description: Use when creating a new social science research project harness or adapting an existing project to the lightweight local research harness structure.
---

# Project Harness Initializer

## 用途

用于新建论文项目，或把已有项目整理成个人社会科学研究 harness。目标是建立一个够用、轻量、可被 Claude Code、Codex 和其他本地 agent 共同理解的项目入口。

不要把初始化做成企业级项目框架。项目层只保存当前项目运行所需的少量稳定信息。

## 先读什么

按需读取，不要一次读完整 harness：

1. `~/.research_harness/README.md`
2. `~/.research_harness/FILE_MAP.md`
3. `~/.research_harness/RESEARCH_PROFILE.md`
4. `~/.research_harness/templates/` 中本次需要复制的模板

如果项目已经存在，先检查现有目录结构。不要静默覆盖、删除或重命名已有文件。

## 默认核心文件

项目启动时默认只创建这些核心文件：

```text
harness/PROJECT_CONTEXT.md
harness/VARIABLES.md
harness/OUTPUT_SPEC.md
analysis_notes/INDEX.md
```

常用入口文件：

```text
README.md
CLAUDE.md
AGENTS.md
```

`BLUEPRINT.md` 只在进入写作规划阶段后生成，除非用户明确要求提前创建。

## 推荐目录

如果用户没有既有结构，可建议以下最小结构；如果已有 `data/`、`code/`、`draft/`、`figure/`、`table/`、`literature/`，优先沿用。

```text
Project_Name/
├── data/              # derived, temp, dictionary；通常不放大型原始数据
├── code/              # 清洗、描述、模型、表图、日志
├── analysis_notes/    # INDEX.md 与 round_memos/
├── draft/             # outline, sections, full_draft, revision_notes
├── figure/            # exploratory, final
├── table/             # exploratory, final
├── literature/        # matrix, core_literature, background_literature, snowballing, synthesis
├── harness/           # PROJECT_CONTEXT.md, VARIABLES.md, OUTPUT_SPEC.md
├── README.md
├── CLAUDE.md
└── AGENTS.md
```

大型公开调查数据库默认可能位于：

```text
/Users/wenbohu/课程资料/数据
```

不要把原始数据复制进项目，除非用户明确要求。项目 `data/` 通常保存派生数据、临时数据、变量字典和项目级分析数据。

## 初始化流程

1. 判断项目是新建还是已有。
2. 读取现有目录，保留用户已有习惯。
3. 创建缺失目录和核心 harness 文件。
4. 从模板填入已知信息；未知变量、样本、模型、数据位置留空，不编造。
5. 在 `README.md` 和 `PROJECT_CONTEXT.md` 中写清楚原始数据位置、当前阶段和下一步。

## 不做什么

- 不默认创建 `STATE.md`、`DECISIONS.md`、`STORYLINE.md` 或 `LITERATURE_PROTOCOL.md`。
- 不在项目启动时创建 `BLUEPRINT.md`。
- 不把分析历史塞进 `PROJECT_CONTEXT.md`。
- 不移动或修改中心数据仓库中的原始数据。
- 不为未知研究问题、变量定义、样本限制或模型策略补写内容。

## 结束报告

结束时简要说明：创建了哪些目录和文件；哪些文件因已存在而跳过；哪些信息仍需用户补充；下一步最适合进入哪个 workflow。
