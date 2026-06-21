# OUTPUT_SPEC.md

## 文件说明

本文件记录本项目表格、图形、回归表、草稿文档和最终输出的项目特殊要求。跨项目通用规则见：

```text
shared_rules/table_figure_style.md
shared_rules/code_style.md
```

本文件只写本项目需要覆盖或补充的要求，不复制全局规则。

## 总体输出风格

- 默认目标：论文 draft / 附录 / 学术分享 / 其他：
- 写作语言：
- 目标期刊或提交对象：
- 是否有期刊格式要求：
- 需要避免的特殊格式：

默认保持简洁、克制、学术化。除非用户明确要求，不生成网页报告、商业展示、卡片式布局或彩色表头。

## 输出目录

```text
table/exploratory/
figure/exploratory/
table/final/
figure/final/
draft/sections/
draft/full_draft/
draft/revision_notes/
analysis_notes/round_memos/
```

本项目特殊输出目录：

- 

## 文件命名

本项目命名约定：

- 探索性输出：
- final 输出：
- 附录输出：
- 草稿文件：

全局命名原则见 `shared_rules/table_figure_style.md`。

## 表格要求

- 描述统计表是否需要加权：
- 是否按组展示：
- 是否同时展示总样本和分组样本：
- 正文表和附录表如何区分：
- 控制变量是否完整展示：
- 表下注释需要说明：

全局表格风格见 `shared_rules/table_figure_style.md`。这里只记录本项目特殊要求。

## 回归表要求

- 标准误类型：
- 是否使用权重：
- 是否使用固定效应：
- 是否使用聚类：
- 是否需要模型统计量：
- 是否需要附录完整表：
- 显著性标记规则：

标准误和表下注释全局原则见 `shared_rules/table_figure_style.md`。

## 图形要求

- 默认格式：pdf / png / svg / tif
- 是否需要黑白可读：
- 是否需要置信区间：
- 是否需要分组展示：
- 是否进入正文或附录：
- 本项目已有图形风格或 Stata/R theme：

全局图形风格见 `shared_rules/table_figure_style.md`。这里只记录本项目特殊要求。

## Caption 与表下注释

final 表格和图形应配有可进入草稿的标题和注释。本项目特殊 caption 要求：

- 

## 文档输出

- Word 要求：
- Markdown 要求：
- HTML 要求：
- 是否需要双语输出：
- 是否需要保留 track changes 或 revision notes：

默认接近论文 draft。全局文档输出风格见 `shared_rules/table_figure_style.md`。

## 特别避免

- 
- 
- 

## 任务结束汇报

每次生成表格、图形或文档后，AI 应报告文件位置、是否覆盖、是否符合本文件要求，以及是否需要更新 `PROJECT_CONTEXT.md`、`VARIABLES.md`、`OUTPUT_SPEC.md` 或 `BLUEPRINT.md`。
