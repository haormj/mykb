# Tasks

## 1. 数据模型与迁移

- [x] 1.1 新增 Alembic 迁移：建 `weknora_index_versions`、`weknora_concept_map`，给 `knowledge_bases` 加可空列 `active_weknora_version_id`；验证 `alembic upgrade head` 后三处结构存在、`alembic downgrade -1` 可干净回退。
- [x] 1.2 在 `mykb/db/models.py` 增加对应 ORM 模型与关系（含 `UNIQUE(kb_id, git_commit)`、`UNIQUE(weknora_kb_id)`、`UNIQUE(version_id, concept_id)`）；用测试建/删记录验证唯一约束生效。

## 2. 后端插件契约与平台编排层

- [x] 2.1 新增 `mykb/retrieval/backend.py`：`RetrievalBackend` 协议 + `Capabilities`/`SnapshotRef`/`BuildProgress`/`BackendHit`；写一个最小 fake 后端验证协议可被实现、类型检查通过。
- [x] 2.2 实现 `ConceptMapStore` 与 `ActiveResolver`（按 `kb_id` 读写 `active_weknora_version_id`、写 `doc_ref↔concept_id`）；单元测试覆盖"无 active"与"有 active"两种解析结果。
- [x] 2.3 实现 `SnapshotPublisher` 编排（create_snapshot→poll→全部就绪才 activate；任一失败回滚并 `delete_snapshot`；按 `(kb_id, commit)` 幂等；保留 N 版并清理 `retired`）；用 fake 后端测试全有或全无、幂等、清理。
- [x] 2.4 把本地引擎包装成 `LocalBackend`（内存快照契约，同步就绪）；验证既有本地检索测试全部通过。
- [x] 2.5 改造读路径：移除 `RetrievalCache.get(sync=True)`/`build_retrieval_service(sync=True)` 的隐式同步，`RetrievalService.search` 经 `ActiveResolver` 选快照；新增测试断言"首次检索不触发任何发布/物化"。

## 3. WeKnora 适配器

- [x] 3.1 确认真实 `/knowledge-search` 结果中用于映射的文档标识字段（对 dev 实例调用一次或查 Swagger）；把结论写进 `design.md` 的 Open Questions 或新增说明，未确认前不改映射架构。
- [x] 3.2 实现 `mykb/retrieval/engines/weknora/client.py`（建库/上传 manual/查 parse 状态/检索/删除/health，`X-API-Key`+`X-Tenant-ID`，超时与退避）；用 `httpx.MockTransport` 覆盖请求路径与载荷，测试通过。
- [x] 3.3 实现 `WeKnoraBackend` 落 `RetrievalBackend` 契约（create_snapshot 建库+逐 concept 导入并回收 `doc_ref`，poll 汇总 `parse_status`，search 传 `knowledge_base_ids` 并按 `doc_ref` 返回）；契约测试通过。
- [x] 3.4 能力声明与错误模型（`kind` 不支持返回明确错误；`healthcheck` 走 `GET /health`）；测试覆盖"未声明代码检索时 kind=code 报错"。
- [x] 3.5 配置并入 `Settings`（URL/KEY/TENANT_ID/TIMEOUT/RETENTION，默认 retention=3）；未设 URL 时仍选 `LocalBackend`。测试覆盖两种配置分支。
- [x] 3.6 在 `README.md` 增加 WeKnora 部署与所需 API Key 权限（`retrieve`+`ingest`+`manage_kbs`）配置说明，按文档步骤可完成配置。

## 4. 发布任务与 API

- [x] 4.1 新增 `PublishTask` 模型与状态机辅助（queued/building/indexing/activating/ready/failed，记录 `git_commit`、`doc_total`、`doc_completed`、`error`）；状态流转单元测试通过。
- [x] 4.2 实现发布执行器（提交到 executor，受 per-KB `kb_locks` 串行；调用 `SnapshotPublisher`）；用 fake 后端集成测试"发布期间检索仍服务旧 active、成功后切新 active"。
- [x] 4.3 新增路由 `POST /kbs/{kb_id}/publish`（admin/owner，202 返回 task_id；并发返回 409）、`GET /kbs/{kb_id}/publish/{task_id}`（viewer+）、`GET /kbs/{kb_id}/versions`；API 测试覆盖权限、409、进度字段。
- [x] 4.4 移除 `POST /kbs/{kb_id}/index-sync` 并把 `cli sync-index` 改为发布语义（或移除并新增 `publish`）；测试断言旧路由 404、CLI 行为符合新语义。
- [x] 4.5 更新 README/API 文档中的发布接口说明，按文档示例可调通发布与状态查询。

## 5. 回滚与保留

- [x] 5.1 改造 `IndexRollback`：目标版本在保留窗口且 `ready` 时切指针；测试断言不触发重新物化且检索立即返回旧内容。
- [x] 5.2 超出窗口回滚：用 `concepts_at_commit()` 取旧 commit 概念后重新发布并切换；测试覆盖假后端下的重建路径。
- [x] 5.3 保留策略清理：发布成功后将超出 N 的 `retired` 版本对应 WeKnora 库 best-effort 删除，失败仅记录不回滚 active；测试用 fake 后端断言调用。

## 6. 前端

- [x] 6.1 知识库详情新增"发布"按钮与发布状态（轮询 `publish/{task_id}` 展示 `doc_completed/doc_total`、失败原因）；`npm run build`（或 type-check）通过，手动验证按钮流转。
- [x] 6.2 处理错误态与并发态（进行中禁用/提示、未发布库检索提示）；手动验证三态展示正确。

## 7. 集成验证

- [x] 7.1 端到端（合成后端）：经 API 导入已审知识 → 手动发布 → `/retrieve` 命中概念 → 版本/指针正确；e2e 测试通过。
- [ ] 7.2 真实 WeKnora 冒烟（gated，需实例）：配置专用租户后发布成功、`/retrieve` 返回带 concept_id 的命中、回滚窗口内秒切；记录一次可复现的操作记录。
- [x] 7.3 回归：无 WeKnora 配置时本地模式全部既有测试通过（`make test` 或项目测试命令）。

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived spec reflects the manual-trigger snapshot semantics (定时发布仍为后续项).
