---
type: concept
title: 知识维护
description: mykb 的知识维护能力：传递血缘追踪、源删除时的 claim 级修订、陈旧源检测、页面审计、生命周期状态流转与历史版本回滚，以及这些后端能力当前与 API/UI 的接入程度。
tags: [maintenance, lineage, staleness, audit, rollback, lifecycle]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-0a1a041fbc31da9e481eb3a4
    resource: repo://frontend/src/pages/Maintenance.tsx
  - id: openwiki-source-70832f0dba3eb1ab3fd9ad28
    resource: repo://mykb/extraction/harness.py
  - id: openwiki-source-4ccdf13c8842742626ab4110
    resource: repo://mykb/extraction/pipeline.py
  - id: openwiki-source-3cfba03980d2b096a190af71
    resource: repo://mykb/maintenance/audit.py
  - id: openwiki-source-c965ab89b70f36eea1b5be66
    resource: repo://mykb/maintenance/lifecycle.py
  - id: openwiki-source-a443b6dff9bd2a41ffa692ac
    resource: repo://mykb/maintenance/lineage_trace.py
  - id: openwiki-source-280115dcc29863094c300be2
    resource: repo://mykb/maintenance/rollback.py
  - id: openwiki-source-74b3f1ba9a80ddf733264fe6
    resource: repo://mykb/maintenance/staleness.py
  - id: openwiki-source-4c2fbad36351b6670606b9ea
    resource: repo://mykb/okf/model.py
  - id: openwiki-source-7dc8f0150acafc9ffaffbc8c
    resource: repo://tests/test_extraction_pipeline.py
  - id: openwiki-source-c8ebe214422c05d44d8164ea
    resource: repo://tests/test_maintenance.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 知识维护

`mykb/maintenance` 集中实现“知识积累之后的保养”：谁依赖谁、源过期了怎么办、页面整体是否健康、如何标记废弃、如何回退到历史版本。需要先看清现实：这些模块大多是**库级能力**，目前只有血缘追踪被提取流水线直接调用；审计、陈旧检测、回滚、生命周期状态等尚未暴露为 HTTP 接口，前端「知识维护」也只是占位页。本文如实区分“已接入”和“已实现但未接线”。

## 与流水线的接入现状

- **已接入**：`trace_affected` 被 `mykb/extraction/pipeline.py` 用于确定一份源文档影响哪些业务知识（`mykb/extraction/pipeline.py:20`）。
- **未接入 API/UI**：`run_audit`、`detect_stale_sources`、`IndexRollback`、`deprecate`、`mark_needs_review`、`re_draft` 仅由测试或库调用方使用，没有对应的路由；前端 `/maintenance` 渲染 `Empty` 占位（`frontend/src/pages/Maintenance.tsx:1`）。

因此下面的能力描述的是“当前代码库实现的语义”，而不是用户可点击的功能。

## 血缘追踪

`trace_affected(bundle, source_id)` 返回所有**传递依赖**该源的业务知识（`mykb/maintenance/lineage_trace.py:8`）：

- 在所有 `knowledge/` 概念上做广度式前沿扩展：初始前沿是源 id，反复把 `sources` 包含前沿成员的概念加入结果并形成下一层前沿；
- 因此融合型知识（由其它知识再派生）也会被到达；
- 返回按 id 排序的去重列表。

这是“按 claim/来源增量修订而非整页重写”的基础。提取流水线用它决定：对受影响页面复用标题与来源、结合新源重新提炼，而不是新建孤页。

## 源删除时的 claim 级修订

删除源文档时，`_delete_and_revise` 会调用 harness 的 `revise_for_removed_source`（`mykb/extraction/harness.py:234`）：

- 从受影响页面的 `claims` 中剔除引用了被删源的条目；
- 若无 claim 存活，则整页删除（页面失去全部证据）；
- 否则保留存活的 claim，重算 `sources` 列表，把 `status` 置为 `needs-review`，并重写 `## 要点` 正文。

这保证了“删一个源”不会误删仍被其它来源支撑的知识，也不会留下悬空的 claim。

## 陈旧与变更检测

`staleness.py` 提供源级新鲜度检测（`mykb/maintenance/staleness.py:1`）：

- `is_expired` 解析概念 frontmatter 的 `stale_after`（ISO 时间），到期即视为过期；缺失或无法解析则不判过期。
- `detect_stale_sources` 遍历 `raw/` 概念，收集 `stale_after` 已过期者，并可选传入 `resource_checker` 探针来识别外部 `resource` 已变更的源（HTTP head、git ref、文件 mtime 等由调用方实现）。返回 `StaleSource(concept_id, reason)`，reason 为 `stale_after` 或 `resource_changed`。

当前没有内置的 `resource_checker`，也没有定时任务触发检测。

## 页面级审计

`audit_knowledge` 把每页当作整体检查，因为逐文档评审只看增量（`mykb/maintenance/audit.py:1`）：

- 复用 `validate_concept` 的语义校验（type、title、claim 来源、断链、重复标题）；
- 额外检测**页内重复 claim**；
- 检测 frontmatter 中的 `x-conflicts`（声明的冲突待解决）。

`run_audit` 在发现问题后，对所有受影响页面调用 `mark_needs_review`（reason=`page audit`），从而让问题页退出“stable”可检索状态、等待人工处理。测试 `test_page_audit_flags_and_marks_needs_review` 覆盖了重复 claim 等场景。

## 生命周期状态

`lifecycle.py` 提供三种状态操作（`mykb/maintenance/lifecycle.py:1`）：

- `mark_needs_review(bundle, ids, reason)`：把概念 `status` 置为 `needs-review`，可选写入 `x-review-reason`；
- `deprecate(bundle, concept_id, superseded_by=...)`：置 `status: deprecated` 并写入 `superseded_by`，指向替代页面；
- `re_draft(bundle, concept_id, drafter, ...)`：从该概念原始 `sources` 重新提取一份新草稿（要求存在来源，否则报错）。

这些状态与 `is_verified_stable()` 配合：一旦离开 `stable`，该知识就不再满足检索可见性条件。

## 历史版本回滚

`rollback.py` 基于 git 提交与已发布快照做回退（`mykb/maintenance/rollback.py:1`）：

- `concepts_at_commit(bundle, commit)` 用 `git ls-tree`/`git show` 读取指定提交下 `knowledge/` 的概念，只保留当时 `verified && stable` 的页面。
- `IndexRollback.rollback(session, kb_id, version)`：
  - 若该库在 `weknora_index_versions` 中已有对应 `git_commit` 且状态 `READY` 的快照，则**只移动 active 指针**激活它（秒级回退）；
  - 否则从该 git 提交重建概念集合，用 `SnapshotPublisher` 发布一个新快照；
  - 该提交下没有合格知识时抛 `RollbackError`。

这利用了“不可变快照 + active 指针”的发布模型，详见 [检索与快照发布](../retrieval/retrieval-and-publish.md)。

## 能力与实践的关系

| 能力 | 模块 | 是否已接入 API/UI |
| --- | --- | --- |
| 传递血缘 | `lineage_trace.trace_affected` | 是（提取流水线内部） |
| 源删除 claim 修订 | `harness.revise_for_removed_source` | 是（删除文档流程） |
| 陈旧/变更检测 | `staleness.*` | 否 |
| 页面审计 | `audit.*` | 否 |
| 状态流转（needs-review/deprecated/re-draft） | `lifecycle.*` | 否 |
| 历史回滚 | `rollback.IndexRollback` | 否 |

## 代表测试

`tests/test_maintenance.py` 覆盖过期与变更检测、传递血缘、`mark_needs_review` 与 `re_draft`、`deprecate` 指向替代页、以及 `IndexRollback` 恢复历史版本；`tests/test_extraction_pipeline.py` 覆盖删除文档时按 claim 修订知识。
