---
type: concept
title: 文档级评审与合并
description: 每份源文档一个 change 分支构成文档级 MR、按库单飞的串行评审、审批/拒绝/退回重做、verified 与 stable 标记，以及提取项与导入任务的状态流转。
tags: [review, workflow, git, merge, approval, state-machine]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-a915535882e02732916427f3
    resource: repo://mykb/api/routes/review.py
  - id: openwiki-source-4ccdf13c8842742626ab4110
    resource: repo://mykb/extraction/pipeline.py
  - id: openwiki-source-e505b7019d6a17328bbf6e7c
    resource: repo://mykb/extraction/queue.py
  - id: openwiki-source-17b206086749553c2ec1a4e4
    resource: repo://mykb/extraction/review.py
  - id: openwiki-source-7dc8f0150acafc9ffaffbc8c
    resource: repo://tests/test_extraction_pipeline.py
  - id: openwiki-source-02a88f838799ec6965ae776e
    resource: repo://tests/test_extraction.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 文档级评审与合并

mykb 的评审单位是**文档**，不是单个知识页。每份源文档在提取时生成一条独立 git 分支，内容包含该文档的 raw 概念以及受它影响的业务知识变更，合起来就是一个“文档级 MR”。人工只评审、不改写正文；`knowledge/` 由 AI 撰写。未合并的分支不影响主干，也不进入检索。

## 为什么是文档级 MR

一份源文档可能同时影响多个已存在的业务知识页面（通过血缘传递闭包），如果按页面逐个评审，会割裂同一份来源带来的耦合变更。把“源 + 其引发的知识变更”打包成一个分支，评审者能在一个 MR 里看到一致的整体，也让同一库的变更串行推进，避免共享知识页冲突。

这一策略由 `mykb/extraction/pipeline.py`（构建分支）与 `mykb/extraction/review.py`（合并与标记）共同实现。

## 状态机

提取项（`ExtractionItem.status`）与导入任务（`ImportTask.status`）是两层状态：

**提取项**（`mykb/extraction/queue.py:16`）：

```
queued → processing → reviewing → merged | rejected
              └──────────────→ failed
```

- `queued`：待处理；
- `processing`：被 worker 领取，正在构建分支；
- `reviewing`：分支已建好，等待人工评审；
- `merged` / `rejected` / `failed`：终态。

**导入任务**由提取项聚合而来（`refresh_import_task_status`，`mykb/extraction/queue.py:137`）：存在 `reviewing` 则任务 `reviewing`，否则有 `processing/queued-for-review/queued` 则 `queued-for-review`，全部 `merged` 则 `merged`，全部 `rejected` 则 `rejected`。导入任务若已是 `failed`/`cancelled` 则不再被覆盖。

## 单飞与串行

同一知识库同时只允许一个打开的 MR。`has_open_review` 检查是否存在 `processing`/`queued-for-review`/`reviewing` 的项（`mykb/extraction/queue.py:64`）；`process_pending` 据此在循环开头停止，只有当前 MR 被合并或拒绝后才取下一份。

合并/拒绝/重做完成后，`approve_item`、`reject_item`、`redraft_item` 都会再次调用 `process_pending`，从而串行推进队列——同一库一次推进一份，不同库可并行。

## 审批（approve）

`approve_item` 的处理顺序（`mykb/extraction/pipeline.py:207`）：

1. 校验项存在且状态为 `reviewing` 且有分支，否则抛 `PipelineError`。
2. 计算分支相对 `main` 的变更文件。
3. `merge_branch`（`--no-ff`）合并到 `main`。
4. 遍历变更中属于 `knowledge/*.md` 且仍存在的概念，调用 `stamp_verified`：把 `status` 置 `stable` 并追加 `{"by": "human:<reviewer>", "at": ...}` 到 `verified`（`mykb/extraction/review.py:29`）。
5. 若有标记则提交一条 `ci: verify <branch> (human:<reviewer>)`。
6. 若配置了远程则推送，删除分支、清理暂存、标记 `merged`、刷新导入任务状态、使检索缓存失效。
7. 最后继续 `process_pending` 推进下一份。

只有审批后业务知识才同时具备 `verified` 与 `stable`，从而满足检索可见性条件。

## 拒绝（reject）

`reject_item` 校验状态为 `reviewing` 后删除该分支（不合并、不打标记），清理暂存，标记 `rejected` 并刷新任务状态，再推进队列（`mykb/extraction/pipeline.py:269`）。被拒绝的变更不会落在 `main`。

## 退回重做（redraft）

“部分接受”场景：raw 合格但知识不合格时，`redraft_item` 删除原分支、删除已生成的 knowledge 草稿，把项重新置为 `queued`（`branch=None`），再调用 `process_pending` 重新提取到同一 MR（`mykb/extraction/pipeline.py:310`）。这允许保留已接受的源数据而只重做知识部分。

注意：`reject` 与 `redraft` 都会删除分支，但 `redraft` 会把项放回队列而非进入终态。

## 旧的草稿级审阅路径

除文档级 MR 外，`GitReview` 还提供更细粒度的草稿分支能力（`submit`/`approve`/`reject`），分支名 `review/<concept slug>`，审批时会合并并用 `stamp_verified` 标记（`mykb/extraction/review.py:85`）。API 的 `/review/drafts`、`/review/approve` 走这条路径，服务单页草稿的一键审核；`/review/mrs/*` 走文档级 MR 路径。两条路径共享“合并后再标记”的思路。

## API 与前端

- `GET /kbs/{kb_id}/review/mrs` 列出 `reviewing/queued/processing` 的项；`GET /review/mrs/{id}/diff` 用三点 diff 展示分支相对 `main` 的变更；`POST /review/mrs/{id}/approve|reject|redraft` 触发上述三种操作（`mykb/api/routes/review.py:81`）。
- 这些端点全部要求知识库 `admin` 角色。
- 前端在知识库详情的「草稿审核」页展示 MR 列表与 diff，并提供审批/拒绝/退回操作（详见 [前端应用](../frontend/web-application.md)）。

## 失败与恢复

- 构建分支失败：`_recover_to_main` 强制回 `main` 并 reset，项标 `failed`，队列继续。
- 进程重启：启动时 `recover_processing` 把残留 `processing` 项重置为 `queued`，可续跑（`mykb/extraction/queue.py:114`）。
- 导入任务取消：`process_pending` 发现父任务已 `cancelled` 时清理暂存并标记 `rejected`，不建分支。

## 代表测试

`tests/test_extraction.py` 覆盖 `stamp_verified` 与 git 审批/拒绝不落主干；`tests/test_extraction_pipeline.py` 覆盖导入→审批流程、modify MR、拒绝与重做、队列状态机与 `recover_processing`；`tests/test_review_api.py` 覆盖评审 API 的鉴权与 MR 流转。
