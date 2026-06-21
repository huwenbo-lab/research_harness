# Project README

## 文件说明

本文件说明项目目录和使用方式。它不是论文说明书，也不是当前研究主线文件。

当前研究主线写在 `harness/PROJECT_CONTEXT.md`；变量说明写在 `harness/VARIABLES.md`；输出格式写在 `harness/OUTPUT_SPEC.md`；分析历史由 `analysis_notes/INDEX.md` 索引。

## 最小核心文件

```text
harness/PROJECT_CONTEXT.md
harness/VARIABLES.md
harness/OUTPUT_SPEC.md
analysis_notes/INDEX.md
```

写作阶段再使用：

```text
draft/outline/BLUEPRINT.md
```

## 推荐目录

```text
Project_Name/
├── harness/
│   ├── PROJECT_CONTEXT.md
│   ├── VARIABLES.md
│   └── OUTPUT_SPEC.md
├── analysis_notes/
│   ├── INDEX.md
│   └── round_memos/
├── code/
├── data/
│   ├── derived/
│   ├── temp/
│   └── dictionary/
├── draft/
│   ├── outline/
│   ├── sections/
│   ├── full_draft/
│   └── revision_notes/
├── figure/
│   ├── exploratory/
│   └── final/
├── table/
│   ├── exploratory/
│   └── final/
├── literature/
├── CLAUDE.md
└── AGENTS.md
```

项目已有结构时，优先遵守现有结构，不为完整而强行新增空目录。

## 数据说明

- source data 位置：
- derived data 位置：
- questionnaire / codebook：
- 关键样本限制：

中央数据仓库中的原始数据不得被修改、覆盖或移动。项目目录中的 `data/` 主要保存 derived data、temporary data 和变量说明。

## 使用顺序

AI 进入项目后先读：

```text
harness/PROJECT_CONTEXT.md
harness/VARIABLES.md
harness/OUTPUT_SPEC.md
analysis_notes/INDEX.md
```

进入写作阶段后再读：

```text
draft/outline/BLUEPRINT.md
```

不要默认读取所有 `analysis_notes/round_memos/`。

## 输出规则

项目输出路径和格式要求见 `harness/OUTPUT_SPEC.md`。analysis memo 进入 `analysis_notes/round_memos/`，并由 `analysis_notes/INDEX.md` 索引。

## 注意事项

- 当前 storyline 以 `harness/PROJECT_CONTEXT.md` 为准。
- 进入写作阶段后，论文结构和段落执行以 `draft/outline/BLUEPRINT.md` 为准。
- 历史分析过程进入 `analysis_notes/`，不要塞进当前上下文。
