# INSTALL_OR_COPY_INSTRUCTIONS.md

## 1. 安装全局 harness

推荐位置：

```bash
mkdir -p ~/.research_harness
cp -R research_harness/* ~/.research_harness/
```

如果当前包位于其他路径，将 `research_harness` 替换为实际路径：

```bash
mkdir -p ~/.research_harness
cp -R /path/to/research_harness/* ~/.research_harness/
```

安装后先确认这些文件存在：

```text
~/.research_harness/README.md
~/.research_harness/OVERVIEW.md
~/.research_harness/RESEARCH_PROFILE.md
~/.research_harness/FILE_MAP.md
~/.research_harness/shared_rules/
~/.research_harness/workflows/
~/.research_harness/templates/
~/.research_harness/skills/
```

## 2. 配置 agent 入口

Claude Code 可使用：

```text
~/.research_harness/agent_entries/global/CLAUDE.md
```

Codex 或其他 coding agent 可使用：

```text
~/.research_harness/agent_entries/global/AGENTS.md
```

根据具体工具要求复制或改写到 user-level 入口位置。入口文件应只负责读取顺序、任务路由和优先级，不复制整个 harness。

## 3. 最小项目初始化

在新项目目录中创建最小结构：

```bash
mkdir -p harness
mkdir -p analysis_notes
```

复制默认核心文件：

```bash
cp ~/.research_harness/templates/PROJECT_CONTEXT_template.md harness/PROJECT_CONTEXT.md
cp ~/.research_harness/templates/VARIABLES_template.md harness/VARIABLES.md
cp ~/.research_harness/templates/OUTPUT_SPEC_template.md harness/OUTPUT_SPEC.md
cp ~/.research_harness/templates/analysis_notes_index_template.md analysis_notes/INDEX.md
cp ~/.research_harness/templates/project_readme_template.md README.md
cp ~/.research_harness/templates/project_CLAUDE_template.md CLAUDE.md
cp ~/.research_harness/templates/project_AGENTS_template.md AGENTS.md
```

默认核心文件是：

```text
harness/PROJECT_CONTEXT.md
harness/VARIABLES.md
harness/OUTPUT_SPEC.md
analysis_notes/INDEX.md
```

## 4. 可选项目目录

根据项目需要再创建：

```bash
mkdir -p data/{derived,temp,dictionary}
mkdir -p code/logs
mkdir -p analysis_notes/round_memos
mkdir -p draft/{outline,sections,full_draft,revision_notes}
mkdir -p figure/{exploratory,final}
mkdir -p table/{exploratory,final}
mkdir -p literature/{matrix,core_literature,background_literature,snowballing,synthesis}
```

不要默认把大型 raw data 复制到项目目录。大型公开社会调查数据库通常保留在中央数据仓库，例如：

```text
/Users/wenbohu/课程资料/数据
```

项目目录中的 `data/` 通常保存派生数据、临时数据、变量字典和项目分析数据。

## 5. 写作阶段再创建 BLUEPRINT

只有当项目进入 writing blueprint 阶段时，再创建：

```bash
mkdir -p draft/outline
cp ~/.research_harness/templates/BLUEPRINT_template.md draft/outline/BLUEPRINT.md
```

`BLUEPRINT.md` 是写作阶段的段落级执行规格，不是项目初始化时的默认文件。

## 6. 维护原则

不要默认创建：

```text
STATE.md
DECISIONS.md
STORYLINE.md
```

保持 `PROJECT_CONTEXT.md` 简短且当前有效。分析历史进入 `analysis_notes/`，并由 `analysis_notes/INDEX.md` 索引。进入写作阶段后，论文结构和段落安排以已确认的 `BLUEPRINT.md` 为准。
