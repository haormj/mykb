---
type: concept
title: 检索与快照发布
description: mykb 的统一检索接口、可插拔快照后端、仅 verified&&stable 可检索的索引规则、手动发布全量物化快照、active 指针原子切换、概念映射还原、版本保留与回滚及发布任务状态机。
tags: [retrieval, publish, snapshot, versioning, backend, rollback]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-cd33e70fba9662f391105f04
    resource: repo://mykb/api/routes/publish.py
  - id: openwiki-source-1e4c2d7d725fb278c143221d
    resource: repo://mykb/kb/context.py
  - id: openwiki-source-4c2fbad36351b6670606b9ea
    resource: repo://mykb/okf/model.py
  - id: openwiki-source-5301730fd29f62a8bbf8fb76
    resource: repo://mykb/retrieval/backend.py
  - id: openwiki-source-c0d47e5696245fc0c3935300
    resource: repo://mykb/retrieval/engines/local.py
  - id: openwiki-source-a8f7f60ae29342e5de080518
    resource: repo://mykb/retrieval/index.py
  - id: openwiki-source-79bee293ad80b500d24f1121
    resource: repo://mykb/retrieval/interface.py
  - id: openwiki-source-abbe81a7773046eadbc9c4c3
    resource: repo://mykb/retrieval/publish.py
  - id: openwiki-source-6e885b3cc2fc4659c9941bad
    resource: repo://mykb/retrieval/read.py
  - id: openwiki-source-19b1b14022552aa86d4c9e42
    resource: repo://mykb/retrieval/service.py
  - id: openwiki-source-e80c2a036f583e4e956ed1aa
    resource: repo://mykb/retrieval/tasks.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 检索与快照发布

检索与内容写入是解耦的：合入 `main` 的新知识不会自动可搜，必须由 admin/owner 手动**发布**，把当前提交下合格的业务知识全量物化为一个不可变快照，并在就绪后原子切换 active 指针。读路径只读 active 快照，因此发布期间检索继续服务上一个版本。本文说明检索接口、后端契约、发布编排与任务状态。

## 两层检索服务

平台有两种检索服务形态，共享相同的响应结构：

- **`RetrievalService`**（离线/CLI）：直接持有知识引擎与可选代码引擎，`search` 按 `kind` 路由，`answer` 取首条命中片段或调用 answerer（`mykb/retrieval/interface.py:49`）。
- **`SnapshotRetrievalService`**（平台）：在每次查询时从数据库解析该库的 active 快照，调用后端并在快照内搜索，再把后端文档 id 映射回平台概念 id（`mykb/retrieval/read.py:13`）。

`build_retrieval_service` 依据是否传入 `session_factory` + `kb_id` 决定返回哪一种；未配置 `MYKB_WEKNORA_URL` 时后端为本地内存实现，否则为 WeKnora（`mykb/retrieval/service.py:13`）。

## 响应与命中

`RetrievalHit` 包含 `concept_id`、`title`、`snippet`、`score`、`engine`；`RetrievalResponse` 包含 `query`、`kind`、`engine`、`hits` 与 `knowledge_version`（`mykb/retrieval/interface.py:18`）。`knowledge_version` 在平台路径上取快照的 `git_commit`。

## 后端契约

平台把“版本、指针、概念映射、保留”留在自身，后端只负责四件事（`mykb/retrieval/backend.py:1`）：

- `create_snapshot(concepts, label)` → `SnapshotRef`；
- `poll(ref)` → `BuildProgress`（`building`/`ready`/`failed`，含 `concept_docs` 映射）；
- `search(query, ref, top_k)` → `BackendHit`（按后端文档 id）；
- `delete_snapshot(ref)`，以及 `healthcheck()`。

`Capabilities` 声明是否支持代码、生成、异步 ingest。`LocalBackend` 为每个快照建一个隔离的进程内 markdown RAG，`poll` 立即 ready，`concept_docs` 是概念 id 到自身的映射（`mykb/retrieval/engines/local.py:16`）。WeKnora 后端细节见 [WeKnora 集成](weknora-integration.md)。

## 什么能进索引

`select_indexable_knowledge` 只选择 `knowledge/` 下满足 `is_verified_stable()` 的概念——即 `status == "stable"` 且有 `verified` 记录（`mykb/retrieval/index.py:9`、`mykb/okf/model.py:145`）。`select_code_sources` 把 `type: 代码` 的 raw 概念单独挑出来喂给代码引擎，而不是 RAG 索引。因此“AI 起草但未审批”或“需要复核”的知识不会进入检索。

## 发布编排

`SnapshotPublisher.publish` 是发布核心（`mykb/retrieval/publish.py:116`）：

1. 过滤掉无 id 的概念；为空则 `PublishError("no verified knowledge to publish")`。
2. 若该 `(kb_id, git_commit)` 已有 `ready` 快照，直接激活该版本并返回（幂等重发）。
3. 若已有 `building` 快照，抛“已有发布进行中”。
4. 进入 `building`：后端 `create_snapshot`，写/更新 `WeKnoraIndexVersion`，记录 `doc_total`。若存在同提交的旧记录，先删除其旧后端快照。
5. 进入 `indexing`：轮询 `poll` 直到 `ready`/`failed` 或超时（默认最多 120 次、每次 1s）。失败则标记版本 `failed`、删除后端快照并抛错。
6. 进入 `activating`：用 `progress.concept_docs` 替换 `weknora_concept_map`，把版本置 `ready`、记录 `ready_at`。
7. **原子切换**：`ActiveResolver.activate` 更新 `knowledge_bases.active_weknora_version_id` 指向新版本，flush 后才提交。
8. `_retire_old` 按创建时间倒序保留最近 `retention`（默认 3，最少 1）个 `ready` 版本，更早的置 `retired` 并删除后端快照。

关键点：`active_weknora_version_id` 的更新与新版本 `ready` 在同一事务提交，读路径按指针解析，因此切换是原子的；新版本构建期间指针仍指向旧快照。

## 概念映射

`weknora_concept_map` 保存 `(version_id, concept_id) → doc_ref`（`mykb/retrieval/publish.py:61`）。读路径在激活版本上取 `doc_to_concept` 反向映射，把后端命中还原为平台 `concept_id`；无法映射的命中被丢弃（`mykb/retrieval/read.py:64`）。这使知识库可与任意后端解耦，同时保持平台标识稳定。

## 读路径

`SnapshotRetrievalService.search`（`mykb/retrieval/read.py:44`）：

- `kind == "code"` 时走代码引擎；
- `kind != "knowledge"` 抛 `KeyError`；
- 解析 active 版本；若没有 active 快照则返回空命中；
- 否则构造 `SnapshotRef`、调用后端搜索、映射回 `concept_id`，带 `knowledge_version=version.git_commit` 返回。

读路径从不物化或发布快照，发布只发生在写路径。

## 发布任务与状态机

HTTP 发布是异步任务。`POST /kbs/{kb_id}/publish` 要求 admin；若已有活动任务返回 409，否则记录当前 HEAD（取不到时 `unversioned`）创建 `PublishTask` 并提交后台 worker，返回 202（`mykb/api/routes/publish.py:24`）。

任务状态机（`mykb/retrieval/tasks.py:11`）：

```
queued → building → indexing → activating → ready
   └──────────────┴────────────┴────────────→ failed
```

`advance` 只允许表内合法的转移，非法转移抛 `InvalidTransition`。worker 在按知识库的锁内取任务，置 `building`，读取 `select_indexable_knowledge` 后调用 publisher，并通过 `on_phase` 回调把 `building/indexing/activating` 写回任务；成功置 `ready` 并记录 `version_id` 与文档计数，失败置 `failed` 并写 `error`（`mykb/retrieval/tasks.py:80`）。

同库发布与导入共享锁，因此互相串行；不同库可并行。

## 查询接口

- `GET /kbs/{kb_id}/retrieve?q=&kind=&top_k=`：viewer，返回 `asdict(RetrievalResponse)`。
- `GET /kbs/{kb_id}/answer?q=`：viewer，返回 `{query, answer}`（默认取首条命中片段）。
- `GET /kbs/{kb_id}/publish/{task_id}`：viewer 查看进度。
- `GET /kbs/{kb_id}/versions`：viewer 列出所有快照版本并标记 `is_active`。

`RetrievalCache` 缓存每个库的服务对象，但每次查询都解析 active 指针，所以发布切换无需跨进程失效缓存；审批合并后会显式 `invalidate` 重建服务（`mykb/kb/context.py:18`）。

## 回滚

由于快照不可变且保留最近若干版本，回滚可在保留窗口内**只移动 active 指针**秒级完成；超出窗口时由 `IndexRollback` 从对应 git 提交重建新快照。详见 [知识维护](../maintenance/knowledge-maintenance.md)。

## 代表测试

`tests/test_retrieval.py`、`tests/test_retrieval_backends.py` 覆盖索引选择、快照创建/搜索/映射、发布幂等与保留；`tests/test_weknora_*.py` 覆盖 WeKnora 后端；`tests/test_platform_foundation.py` 覆盖按知识库隔离的检索与 404 旧路由。
