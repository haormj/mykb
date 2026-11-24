---
type: concept
title: WeKnora 集成
description: mykb 与自部署 WeKnora 的集成：客户端协议与鉴权头、workspace API Key 与租户约束、embedding 模型绑定、每个快照一个知识库的建库与入库、解析状态轮询、概念到文档映射与检索结果还原、保留与退役。
tags: [weknora, integration, retrieval, backend, embedding, snapshot]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-c0d47e5696245fc0c3935300
    resource: repo://mykb/retrieval/engines/local.py
  - id: openwiki-source-7e51cc89fba3282d96b1fb8e
    resource: repo://mykb/retrieval/engines/weknora/backend.py
  - id: openwiki-source-4f159177ddea338bd7127686
    resource: repo://mykb/retrieval/engines/weknora/client.py
  - id: openwiki-source-abbe81a7773046eadbc9c4c3
    resource: repo://mykb/retrieval/publish.py
  - id: openwiki-source-6e885b3cc2fc4659c9941bad
    resource: repo://mykb/retrieval/read.py
  - id: openwiki-source-19b1b14022552aa86d4c9e42
    resource: repo://mykb/retrieval/service.py
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-920feb9d6e105be638c84ce4
    resource: repo://tests/test_weknora_engine.py
  - id: openwiki-source-740c4fe6305c1ca7a9295b0e
    resource: repo://tests/test_weknora_retrieval.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# WeKnora 集成

配置 `MYKB_WEKNORA_URL` 后，检索引擎从进程内本地实现切换为自部署的 WeKnora。平台仍掌握版本、指针、概念映射与保留策略，WeKnora 只作为“快照后端”实现 `RetrievalBackend` 协议：每个发布快照对应一个独立的 WeKnora 知识库，每条业务知识概念对应库里的一条文档。本文说明客户端协议、约束与快照生命周期。

## 何时启用

`build_knowledge_backend` 读取 `Settings.weknora_url`：存在则构造 `WeKnoraClient` 与 `WeKnoraBackend`，否则返回 `LocalBackend`（`mykb/retrieval/service.py:13`）。相关配置：

| 变量 | 说明 |
| --- | --- |
| `MYKB_WEKNORA_URL` | WeKnora API 地址，如 `http://weknora:8080` |
| `MYKB_WEKNORA_KEY` | workspace 级 API Key，需 `retrieve`+`ingest`+`manage_kbs` |
| `MYKB_WEKNORA_TENANT_ID` | 专用租户 ID |
| `MYKB_WEKNORA_TIMEOUT` | 请求超时秒数，默认 30 |
| `MYKB_WEKNORA_RETENTION` | 保留最近多少个已发布快照，默认 3 |
| `MYKB_WEKNORA_EMBEDDING_MODEL_ID` | 发布建库时使用的 embedding 模型 id |

## 客户端与鉴权

`WeKnoraClient` 是面向 WeKnora v0.9 API 的轻量 HTTP 客户端（`mykb/retrieval/engines/weknora/client.py:1`）：

- 鉴权头：`X-API-Key`（来自 `MYKB_WEKNORA_KEY`）与可选 `X-Tenant-ID`（来自 `MYKB_WEKNORA_TENANT_ID`）（`mykb/retrieval/engines/weknora/client.py:42`）。
- 响应解包：HTTP ≥400 抛 `WeKnoraError`；非 JSON 抛错；若 JSON 含 `success: false` 抛错；若含 `data` 字段则返回 `data`，否则返回原始 JSON（`mykb/retrieval/engines/weknora/client.py:50`）。
- 重试：对传输错误与 5xx 最多重试 `max_retries`（默认 2）次，采用线性退避；4xx 立即失败（`mykb/retrieval/engines/weknora/client.py:66`）。
- `health()` 请求 `/health` 并要求 `status == "ok"`。

主要方法对应端点：

| 方法 | 端点 |
| --- | --- |
| `create_knowledge_base` | `POST /api/v1/knowledge-bases` |
| `delete_knowledge_base` | `DELETE /api/v1/knowledge-bases/{kb_id}` |
| `add_manual_knowledge` | `POST /api/v1/knowledge-bases/{kb_id}/knowledge/manual` |
| `list_knowledge` / `list_all_knowledge` | `GET /api/v1/knowledge-bases/{kb_id}/knowledge`（分页） |
| `knowledge_search` | `POST /api/v1/knowledge-search` |

## 每个快照一个知识库

`WeKnoraBackend.create_snapshot` 为一次发布新建一个 WeKnora 知识库，名称为 `<prefix>-<label>`（label 通常是 git commit）（`mykb/retrieval/engines/weknora/backend.py:38`）：

1. 调 `create_knowledge_base`，并在请求体带上 `embedding_model_id`（如有）、描述 `mykb published snapshot`；
2. 逐条概念调 `add_manual_knowledge`，标题取 `concept.title`，正文取 `concept.body`；
3. 记录 `concept_id → doc_id` 映射到内存 `_docs`；
4. 返回 `SnapshotRef`（`snapshot_id` 即 WeKnora 知识库 id）。

**embedding 模型绑定**是关键运维点：WeKnora 建库不会自动取租户默认 embedding 模型，若不传 `embedding_model_id`，文档解析会报 `model ID cannot be empty`。因此配置 WeKnora 时必须先把模型 id 填入 `MYKB_WEKNORA_EMBEDDING_MODEL_ID`。测试 `test_backend_create_snapshot_passes_embedding_model_id` 与 `..._omits_empty_...` 固定了该行为。

同样是关键约束：WeKnora 的 API Key 必须是 workspace 级、具备 `retrieve`+`ingest`+`manage_kbs` 能力。**不能**用带 `knowledge_base_ids` 白名单的受限 Key——白名单会挡住每次发布新建的知识库。

## 解析状态轮询

`poll(ref)` 读取该知识库下所有文档并统计解析状态（`mykb/retrieval/engines/weknora/backend.py:61`）：

- `parse_status == "completed"` 计入完成；`"failed"` 计入失败并产生错误信息；
- 任何失败立即返回 `BuildProgress(FAILED, ...)`；
- 全部 completed 返回 `READY`，否则返回 `BUILDING`（带进度）；
- `concept_docs` 随结果返回，供平台建立概念映射。

平台侧 `SnapshotPublisher` 每隔 `poll_interval`（默认 1s）轮询，最多 `max_polls`（默认 120）次；超时按失败处理。这决定了默认约 2 分钟的发布超时上限。

## 检索与结果还原

`search` 调 `knowledge_search`，请求带 `knowledge_base_ids=[快照知识库 id]` 与 `match_count=top_k`（`mykb/retrieval/engines/weknora/backend.py:85`）。响应中每条取 `knowledge_id` 作为 `doc_ref`、`knowledge_title`、`content`、`score`，构造 `BackendHit`。

平台读路径 `SnapshotRetrievalService` 再用 `weknora_concept_map` 把 `doc_ref` 反向映射为 `concept_id`，无法映射的命中被丢弃（`mykb/retrieval/read.py:64`）。因此 WeKnora 返回的是它自己的文档 id，而用户看到的是平台概念标识。

## 保留与退役

发布成功后，`SnapshotPublisher._retire_old` 在 `ready` 版本中按创建时间倒序保留最近 `retention`（默认 3）个，更早的版本置 `status="retired"` 并调用后端 `delete_snapshot` 删除对应 WeKnora 知识库（`mykb/retrieval/publish.py:200`）。`delete_snapshot` 调 `delete_knowledge_base` 并清理内存映射（`mykb/retrieval/engines/weknora/backend.py:108`）。

数据库层面 `weknora_index_versions` 用 `(kb_id, git_commit)` 与 `weknora_kb_id` 两个唯一约束保证同一提交不重复建库、每个快照知识库唯一（见 [平台数据模型](../architecture/data-model.md)）。

## 与平台发布流程的关系

WeKnora 只填了后端契约的“物化/轮询/搜索/删除”四个动作，其余（版本记录、active 指针、概念映射、保留）都由平台 `SnapshotPublisher` 完成。因此发布期间旧快照继续服务，`active_weknora_version_id` 在新快照 ready 后原子切换。测试 `test_publish_task_serves_old_active_until_ready` 验证了构建期间读路径仍返回旧版本、就绪后才看到新知识。详见 [检索与快照发布](retrieval-and-publish.md)。

## 本地后端与旧适配器

- `LocalBackend` 是未配置 WeKnora 时的默认实现：每个快照一个隔离的内存 markdown RAG，`poll` 立即 ready，`concept_docs` 为概念 id 到自身（`mykb/retrieval/engines/local.py:16`）。它面向开发与测试，重启后快照丢失、需重新发布。
- `mykb/retrieval/engines/markdown_rag.py` 里还有一个较早的 `WeKnoraAdapter`（`POST /index`、`POST /search`），与当前 `WeKnoraBackend`（快照知识库模型）不是同一条使用路径；生产路径使用后者。

## 失败语义

- WeKnora 不可达或 5xx：客户端重试后抛 `WeKnoraUnavailable`，发布轮询得到 `FAILED`，任务 `failed` 并记录错误，旧快照保持 active。
- 某文档解析失败：`poll` 立即返回 `FAILED`，整个发布失败并删除新知识库，避免半可用快照。
- 建库缺 embedding 模型：文档解析失败，需要在配置中补 `MYKB_WEKNORA_EMBEDDING_MODEL_ID` 并重新发布。

## 代表测试

`tests/test_weknora_engine.py` 覆盖客户端鉴权与请求体、搜索结果、健康检查、建快照传/不传 embedding 模型、搜索映射、删除与能力、配置解析与本地/WeKnora 选择；`tests/test_weknora_retrieval.py` 覆盖版本/映射唯一约束、发布任务状态机、旧 active 服务到新快照 ready、保留与端点；`tests/test_weknora_e2e.py` 覆盖发布后检索的端到端流程。
