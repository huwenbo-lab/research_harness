# r_and_r.md — 审稿回应（Revise & Resubmit）

## 适用场景

用于投稿后收到期刊 R&R（major / minor revision）决定，或导师、合作者给出综合修改意见之后：系统回应每条意见、按要求补分析与改稿、写 point-by-point response。

本阶段尚无专门 skill。目前由本页 ＋ `final-checker`、`fresh-context-revision` 和分析类 skill 组合完成；自动拆解意见、起草 response、逐条追踪状态的专门 skill 待建。

## 先读文件

先读全局规则：

```text
RESEARCH_PROFILE.md
shared_rules/workflow_principles.md
shared_rules/writing_style.md
shared_rules/table_figure_style.md
```

再读项目文件：

```text
审稿意见 / 编辑信原文
Project/draft/full_draft/            # 现稿
Project/draft/outline/BLUEPRINT.md
Project/harness/PROJECT_CONTEXT.md
Project/harness/VARIABLES.md
Project/harness/OUTPUT_SPEC.md
Project/table/final/
Project/figure/final/
```

需要补分析时，再读相关 analysis memo、代码和结果文件。

## 输入

- 编辑信与每位审稿人的意见（逐条）；
- 哪些是编辑强调的 must、哪些可商榷；
- 篇幅、格式、期限限制；
- 哪些新分析可行、哪些数据不支持。

## 步骤

1. 拆解意见。把每条意见拆成"诉求 ＋ 我方可行回应"，先归类：同意并已改 / 同意将改 / 部分采纳 / 有理由不改。
2. 分派去向。需补分析的回"数据探索·主分析+稳健挡"；需改写的回"成文 / fresh-context 修订"；需澄清的在 response 里说明。
3. 补分析。按要求做稳健性、异质性、替代设定或新模型，记 analysis memo；数据不支持的结论如实说明，不硬凑。
4. 改稿。按意见修订正文，保持与 `BLUEPRINT.md` 一致；若结构或主线确有调整，先更新 `BLUEPRINT.md` 再改稿。
5. 写 response 信。逐条引用意见 → 回应 → 指出稿中改动位置（页/段/表号）；语气专业克制，不过度承诺、不嘴硬、不为迎合而夸大证据。
6. 整体一致性检查。用 `final-checker` 复核修订稿与 response 是否一致、是否引入新的不一致。

## 输出

```text
Project/draft/revision_notes/response_to_reviewers.md   # 逐条回应
Project/draft/full_draft/                               # 修订稿
Project/analysis_notes/round_memos/                     # 补分析 memo
Project/table/final/ · Project/figure/final/            # 更新的表图
```

若主线或结构变化，同步更新 `BLUEPRINT.md` 和 `PROJECT_CONTEXT.md`。

## 停止条件

- 每条意见都有明确回应（已改 / 将改 / 部分采纳 / 有据不改）；
- 需要的补分析已完成并记 memo；
- 修订稿与 response 一一对应、无新的不一致；
- 没有过度承诺，也没有与证据不符的让步；
- 篇幅、格式、期限符合要求。

## 交接

进入再审循环时，保留本轮 decision 与 response；下一轮 R&R 从上一轮 response 续，重点回应"仍未满意"的条目。
