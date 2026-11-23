# Proposal

## Why

检索层已有统一门面，但底层 WeKnora 目前只是一个按"假设契约"写的占位适配器（假设 `POST /index`、`POST /search` 同步返回），无法对接真实 WeKnora：真实后端是异步入库、拥有自己的知识库/文档 ID、按库隔离、需要轮询就绪。同时现有 `RetrievalEngine` 契约过薄（同步 `index`、无 scope、拿不到后端句柄与映射），无法平滑接入 OpenViking 等其它 RAG 后端。

需要先定义一套平台级、后端无关的检索抽象，并据此落地 WeKnora，使后续接入更多 RAG 后端时只新增适配器、不改核心编排逻辑。当前 TODO 也明确要求"数据检索对接支持 WeKnora"。

## What Changes

- 定义平台标准检索分层：**外部稳定接口** / **平台编排层**（版本·快照·指针·映射·保留·发布）/ **后端插件契约**。
- 版本化同步改为**快照语义**：每次发布把当前 `verifying+stable` 业务知识全量物化为后端的一个**全新快照**（WeKnora 知识库），全部就绪后**原子切换 active 指针**。
- 发布改为**手动触发 + 异步任务**（复用 ImportTask 范式：线程池 + DB 任务 + 状态接口）；per-KB 串行；**全有或全无**（任一文档失败即整次失败，保留旧 active）；发布期间检索继续服务旧 active 快照。
- **一条 concept = 后端一条文档**（标题/正文），平台保存 `concept ↔ 后端文档 ID` 映射，用于把检索命中还原成 `concept_id`。
- 保留最近 N 版快照以支持**秒切回滚**；超出保留窗口时用 git 旧 commit 重导。
- 落地真实 WeKnora 适配器（建库 / 上传 manual 文档 / 轮询 parse 状态 / knowledge-search / 删除）。
- **BREAKING**：`POST /kbs/{id}/index-sync` 同步接口改为发布任务；读路径不再隐式触发同步（去掉 `sync=True` on build）；移除占位 `WeKnoraAdapter` 的假设契约。
- 外部 `/retrieve`、`/answer` 的响应结构保持不变；知识库详情新增"发布"入口与发布状态展示。

## Capabilities

### New Capabilities

<!-- 无新增能力：本次是对既有知识检索能力的重定义与落地 -->

### Modified Capabilities

- `knowledge-retrieval`: "版本化同步"由"直接索引当前内容"改为"快照物化 + 指针切换 + 手动异步发布 + 保留/回滚"；"多引擎适配"细化为后端插件契约与平台编排边界；"统一对外接口"明确命中始终归一化为 `concept_id`；"按知识库隔离检索"改为按该库的 active 快照隔离。

## Impact

- 代码：`mykb/retrieval/`（`interface.py`、`service.py`、`engines/*`、`sync.py`、`index.py`）、新增 WeKnora 客户端与发布器、`mykb/maintenance/rollback.py`、`mykb/kb/context.py`、`mykb/api/routes/retrieval.py`、`mykb/cli.py`、`mykb/config.py`。
- 数据库：新增 `weknora_index_versions`、`weknora_concept_map` 两张表，`knowledge_bases` 增加 `active_weknora_version_id` 指针列（Alembic 迁移，仅新增）。
- API：新增 `POST /kbs/{id}/publish`、`GET /kbs/{id}/publish/{task_id}`；旧 `index-sync` 弃用（BREAKING）。
- 前端：知识库详情新增"发布"按钮与发布状态（轮询进度）。
- 外部依赖：自部署开源 WeKnora（专用租户）+ workspace 级 API Key；`httpx` 已在依赖中。
- 保持不变：`kind=code` 仍走本地 codegraph；未配置 WeKnora 时保持本地内存引擎（开发/测试默认）。
