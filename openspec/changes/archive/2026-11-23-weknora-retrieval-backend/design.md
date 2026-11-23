# Design

## Context

See `proposal.md - Why` for motivation. Current implementation and constraints that shape the approach:

- 统一门面在 `mykb/retrieval/interface.py`：`RetrievalEngine` 只有 `name/version/index(concepts, version)/search(query, top_k)`，`RetrievalService` 按 `kind`（`knowledge`/`code`）路由，`answer()` 默认取首条 snippet。
- 引擎装配在 `mykb/retrieval/service.py` 的 `build_default_engines()`：有 `MYKB_WEKNORA_URL` 时用占位的 `WeKnoraAdapter`（假设 `POST /index`、`POST /search`），否则用本地 `LocalMarkdownRAG`；code 用 `LocalCodeGraph`。
- 同步在 `mykb/retrieval/sync.py` 的 `IndexSync`：选 `verified && stable` 概念，调 `engine.index()`，把状态/历史写进 bundle 内 `.mykb/index-state.json`、`index-versions.json`，`version` 取 git HEAD。
- 回滚在 `mykb/maintenance/rollback.py`：`concepts_at_commit()` 从旧 commit 读概念，再 `engine.index()` 重导。
- 运行期缓存在 `mykb/kb/context.py` 的 `RetrievalCache`：按 `kb.id` 缓存 `RetrievalService`，首次 `get()` 时 `sync=True`——即**读路径会触发同步**。
- 触发接口 `POST /kbs/{kb_id}/index-sync`（admin）同步执行；`mykb/cli.py` 有 `sync-index` 命令。
- 异步任务范式已存在：`ImportTask` + `app.state.import_executor`（`ThreadPoolExecutor`）+ `app.state.kb_locks`（per-KB 锁）+ DB 任务状态接口（`api/routes/import_tasks.py`、`extraction/queue.py`）。
- 平台元数据用 SQLAlchemy + Alembic（`mykb/db/models.py`、`migrations/versions/`）；内容存每个知识库的 git 仓库；git+OKF 是唯一事实源。
- 实际 WeKnora 为 v0.9.0：`/api/v1`，API Key（`X-API-Key` + 可选 `X-Tenant-ID`），入库异步（`parse_status`），检索推荐 `POST /knowledge-search`，建库 `POST /knowledge-bases`，导入 Markdown `POST /knowledge-bases/:id/knowledge/manual`，删除 `DELETE /knowledge-bases/:id`。

## Goals / Non-Goals

**Goals:**

- 一套后端无关的检索抽象：外部接口稳定、平台统一管版本、后端只做快照生命周期。
- 以"发布即全量物化新快照 + 指针切换"实现版本化与秒级回滚。
- 落地可运行的真实 WeKnora 适配器，替换占位契约。
- 保持未配置 WeKnora 时的本地开发/测试路径不退化。

**Non-Goals:**

- 不做定时发布调度（仅手动；后续可用外部 cron 调预留的幂等 `publish-due`）。
- 不改 B 分生成链路与 `/answer` 的生成来源（仍用本地 answerer）。
- 不做 WeKnora 生成式问答（`knowledge-chat`）接入。
- 不改 code 检索（仍用本地 codegraph）。
- 不做 per-KB 不同的 embedding 模型配置（用 WeKnora 空间默认）。

## Decisions

### 1. 三层抽象，快照编排归平台

```
外部稳定接口      RetrievalService.search/answer  ->  hits[{concept_id,...}]（结构不变）
      │
平台编排层        SnapshotPublisher · ActiveResolver · ConceptMapStore · PublishTask
      │            （版本 / 指针 / 映射 / 保留 / 发布生命周期，与后端无关）
      │
后端插件契约      RetrievalBackend: capabilities / create_snapshot / poll /
                  search(ref) / delete_snapshot / healthcheck / (可选) answer
      ├── LocalBackend      （内存，同步，dev/test 默认）
      ├── WeKnoraBackend    （本变更落地）
      └── OpenVikingBackend （未来，仅新增适配器）
```

- **理由**：若让每个后端各自管版本/回滚，"保留 N 版、秒切、按库隔离"要在每个后端重写一遍，且行为不一致。
- **备选**：后端各自暴露版本化能力（否决）；平台只做薄转发（否决，无法统一回滚）。

### 2. 快照语义替代就地索引

每次发布把当前 `verified && stable` 概念全量物化为一个**全新的后端快照**（WeKnora：新建一个知识库），全部就绪后原子切换 active 指针；旧快照保留供回滚。

- **理由**：发布期间无半新半旧中间态；回滚 = 改一行指针；与 git commit 一一对应，审计清晰。
- **备选**：单库逐条 upsert + 删除消失文档（否决）：非原子、易错、回滚要反向重算。

### 3. 后端插件契约（我们的标准接口）

概念级契约（设计级，不写具体代码）：

- `Capabilities`: `supports_code`、`supports_generation`、`async_ingest`，用于按 `kind` 路由与明确报错。
- `SnapshotRef`: `{backend, snapshot_id, label(commit)}` 不透明句柄。
- `create_snapshot(concepts, label) -> SnapshotRef`：物化；同一 label 幂等返回既有句柄。
- `poll(ref) -> BuildProgress{status, done, total, error}`：后端异步时轮询就绪。
- `search(query, ref, top_k) -> list[BackendHit{doc_ref,title,snippet,score}]`：命中带后端文档 ID。
- `delete_snapshot(ref)`、`healthcheck()`。
- **映射归平台**：发布结果中的 `doc_ref -> concept_id` 由编排层持久化；检索命中在编排层还原为 `concept_id`，无法映射的命中丢弃。外部 `RetrievalHit`/`RetrievalResponse` 结构不变。

### 4. 数据模型（Postgres，仅新增）

```
weknora_index_versions
  id (pk)
  kb_id              FK -> knowledge_bases
  git_commit         text
  weknora_kb_id      text
  status             text  (building | ready | failed | retired)
  doc_total          int
  doc_completed      int
  error              text null
  created_at, ready_at
  UNIQUE (kb_id, git_commit)     -- 幂等：同一 commit 复用
  UNIQUE (weknora_kb_id)

weknora_concept_map
  id (pk)
  version_id         FK -> weknora_index_versions ON DELETE CASCADE
  concept_id         text
  doc_ref            text       -- 后端文档 ID（WeKnora knowledge_id）
  UNIQUE (version_id, concept_id)

knowledge_bases
  + active_weknora_version_id  FK -> weknora_index_versions, nullable  -- active 指针
```

- **理由**：版本与映射是平台元数据（与评测迁 Postgres 一致），bundle 保持纯 git+OKF。
- **备选**：继续写 bundle 内 `.mykb/*.json`（否决：多进程/审计/查询不便，且与"平台元数据入 DB"不一致）。

### 5. active 指针在查询时按库从 DB 解析

`ActiveResolver` 每次检索按 `kb_id` 读取 `active_weknora_version_id`。`RetrievalCache` 只缓存 service 构造，不再缓存"哪个快照活跃"；发布任务在后台进程切指针，跨进程内存失效不可靠，故必须读 DB。

- **理由**：多 worker / 后台执行安全；指针一翻，下一次查询即生效。
- **备选**：发布成功后回调 web 进程 `cache.invalidate`（否决：跨进程不可保证）。

### 6. 发布 = 手动触发的异步任务（复用 ImportTask 范式）

状态机：

```
queued -> building -> indexing -> activating -> ready
   └────────────── 任一失败 ──────────────────> failed（删半成品快照，指针不变）
```

- 新增 `PublishTask`（DB）+ 提交到 `app.state.import_executor`，受 `kb_locks` per-KB 串行保护；并发发布返回 409。
- 发布期间检索服务旧 active（无旧版本则按未发布处理）。
- **全有或全无**：全部文档 `ready` 才切指针。
- 进度：`doc_completed / doc_total`。

### 7. WeKnora 适配要点（对齐 v0.9.0）

- 认证：workspace 级 API Key（`X-API-Key`，`X-Tenant-ID` 专用租户），权限 `retrieve`+`ingest`+`manage_kbs`。**不用**带 `knowledge_base_ids` 白名单的受限 key——白名单会挡住每次发布会新建的库。
- 建库：`POST /knowledge-bases`，`type=document`，省略 `embedding_model_id`（用空间默认）。
- 导入：每条 concept 调 `POST /knowledge-bases/:id/knowledge/manual`（`title`=title、`content`=body、`status=publish`），记录返回 `Knowledge.id` 为 `doc_ref`。快照全新，无需去重/更新。
- 就绪：`GET /knowledge-bases/:id/knowledge?parse_status=...` 轮询，直到全部 `completed`。
- 检索：`POST /knowledge-search`，`knowledge_base_ids=[active_weknora_kb_id]`，`match_count=top_k`；用结果里的文档 ID 经映射还原概念。
- 清理：失败或超出保留窗口时 `DELETE /knowledge-bases/:id`。
- 超时/重试：HTTP 超时 + 指数退避；`healthcheck` 用 `GET /health`。

### 8. 读路径绝不发布

移除 `RetrievalCache.get(sync=True)` / `build_retrieval_service(sync=True)` 的隐式同步；`cli sync-index` 改为发布语义。构建检索服务只解析 active 指针并调用 `search`。

- **理由**：WeKnora 下"首次检索即建库全量导入"不可接受。

### 9. 回滚

`IndexRollback` 改为：目标版本仍在保留窗口且 `ready` → 切指针；否则 `concepts_at_commit()` + 重新发布一个新快照再切。

### 10. 配置（并入 `Settings`）

`MYKB_WEKNORA_URL`、`MYKB_WEKNORA_KEY`、`MYKB_WEKNORA_TENANT_ID`、`MYKB_WEKNORA_TIMEOUT`、`MYKB_WEKNORA_RETENTION`(默认 3)。未设置 URL 时保持本地引擎。

## API 形态

```
POST /kbs/{kb_id}/publish               (admin/owner) -> 202 {task_id}
GET  /kbs/{kb_id}/publish/{task_id}     (viewer+)     -> {status, git_commit, doc_total, doc_completed, error}
GET  /kbs/{kb_id}/versions              (viewer+)     -> 版本列表（用于回滚/审计，可选）
POST /kbs/{kb_id}/index-sync            -> 移除（BREAKING）
```

- `/retrieve`、`/answer` 响应结构不变。

## Module layout

- `mykb/retrieval/backend.py`：`RetrievalBackend` 协议、`Capabilities`、`SnapshotRef`、`BuildProgress`、`BackendHit`。
- `mykb/retrieval/publish.py`：`SnapshotPublisher`、`ActiveResolver`、`ConceptMapStore`。
- `mykb/retrieval/engines/local.py`：把 `LocalMarkdownRAG` 包装成快照契约的 `LocalBackend`。
- `mykb/retrieval/engines/weknora/`：`client.py`（REST）+ `backend.py`（契约实现）。
- `mykb/db/models.py` + 迁移：新增表与指针列。
- `mykb/api/routes/publish.py`：发布/状态/版本接口。
- `mykb/maintenance/rollback.py`、`mykb/cli.py`、`mykb/config.py`、前端细节页：按上面调整。

## Risks / Trade-offs

- [`SearchResult` 是否稳定携带文档/知识 ID 未在纯文档中 100% 确认] → 编码前用一次真实实例调用确认；若只带 chunk_id，可改为在 `custom_metadata` 存 `concept_id` 或按 chunk→doc 反查，映射表结构不变。
- [大库发布耗时长、占用 executor] → 独立发布执行器或限并发；暴露进度；设置超时与失败重试。
- [每版一个 WeKnora 库导致库数量/空间增长] → 保留 N=3 + 发布后清理 `retired`；`DELETE` 为异步，清理失败仅告警不回滚 active。
- [多进程缓存读到旧 active] → 指针按查询实时 DB 解析，禁止内存缓存活跃版本。
- [WeKnora 空间默认 embedding 不匹配/未配置] → 发布前置校验（`healthcheck` + 建库失败即整次失败并报错）。
- [本地引擎与 WeKnora 双路径行为漂移] → 两者都实现同一快照契约，共用编排层与归一化逻辑；本地路径保留为默认与测试基线。

## Migration Plan

1. Alembic 新增 `weknora_index_versions`、`weknora_concept_map` 与 `knowledge_bases.active_weknora_version_id`（仅新增，可空）。
2. 后端：先落协议与编排层（本地后端适配 + 读路径 DB 解析 + 去掉读时同步），再落 WeKnora client/backend/publisher、`PublishTask` 与路由、回滚、配置、CLI。
3. 前端：知识库详情加"发布"按钮与状态轮询。
4. 数据：不迁移历史；本地模式不受影响；WeKnora 快照在首次手动发布时创建。
5. 回滚：删除新表/列、移除新路由即可；本地引擎与既有内容不受影响。

## Open Questions

- `SearchResult` 文档 ID 字段已确认：每条约结果为 `id`（chunk id）、`knowledge_id`（来源文档 id）、`knowledge_title`、`content`、`score`。映射以 `knowledge_id` 为 `doc_ref`。（来源：WeKnora `website-docs/04-api/02-api-chat.md`，`POST /knowledge-search`。）
- 定时发布：后续用外部 cron 调幂等的 `publish-due` sweep（`HEAD != active.commit` 才发），本变更不实现。
- B 分是否改用后端生成、以及 per-KB embedding 模型配置：均延后。
