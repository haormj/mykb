# Tasks

## 1. 评测数据层（Postgres 模型 + 迁移）

- [x] 1.1 在 `mykb/db/models.py` 新增 `EvalSet`、`EvalCase`、`EvalRun`、`EvalCaseResult` 四张表及外键/级联，遵循现有 `String(36)`/`JSONType`/`_now` 约定；验证：`make typecheck` 通过且 `python -c "from mykb.db import models"` 无导入错误。
- [x] 1.2 新增 Alembic 迁移 `migrations/versions/0004_evaluation_tables.py` 建四表；验证：在临时库执行 `make migrate`（或 `alembic upgrade head`）成功且 `alembic downgrade` 可回退。
- [x] 1.3 新增 `mykb/evaluation/store.py`：题集/题目 CRUD、运行保存（含逐题快照）、按库/按题集查询 trend 与 overview；验证：为 store 新增单测，覆盖创建、列表、跨库运行保存、趋势排序。

## 2. 评分口径（C1）

- [x] 2.1 改造 `mykb/evaluation/runner.py`：输入改为 DB 题集 + 检索服务，按 missing→unverified→not_retrieved→hit/b_only 顺序分类，A 分固定分母、计算 coverage，B 分只对全部题计；验证：新增单测覆盖四类状态与 `b_only` 不计入 A 分分母。
- [x] 2.2 修正空 `expected_concept` 题不再拉低 A 分，并断言 `coverage = (hit+not_retrieved+unverified)/带概念题数`；验证：单测给出固定题集与期望数值。
- [x] 2.3 移除/替换 `EvalSetManager`、`Scoreboard` 中读写 bundle `.mykb`/`evals` 的逻辑，保留 `similarity` 等纯函数；验证：`rg "EvalSetManager|eval-runs|LEVELS"` 无遗留调用点且测试通过。

## 3. OKF 层级调整

- [x] 3.1 将 `mykb/okf/bundle.py` 的 `LEVELS` 改为 `("raw", "knowledge")`，`ensure_layout` 不再创建 `evals/`；验证：新增/更新测试断言新建 bundle 无 `evals` 目录（`tests` 相关用例）。
- [x] 3.2 更新受影响的既有测试与断言（知识库初始化布局、storage/registry 用例）；验证：`make test` 通过。

## 4. 平台级 API 与授权

- [x] 4.1 从 `mykb/api/deps.py` 抽取 `ensure_kb_role(session, user, kb_id, min_role) -> KbAccess`，让 `require_kb_role` 复用它；验证：现有依赖调用测试仍通过。
- [x] 4.2 新增平台级评测路由（`/eval/sets` CRUD、`/eval/sets/{id}/run` 多目标库、`/eval/runs`、`/eval/runs/{id}`、`/eval/sets/{id}/trend`、`/eval/overview`），移除 `/kbs/{kb_id}/eval/*`；验证：接口测试覆盖创建者改删、非创建者只读、批量运行全有或全无、结果库级可见。
- [x] 4.3 运行授权：对每个 `target_kb_ids` 用 `ensure_kb_role(...,"editor")`，结果查询用 `"viewer"`，平台管理员放行；验证：接口测试覆盖 editor 放行、viewer 运行被拒、非成员查结果被拒。
- [x] 4.4 更新 `README.md`「主要接口」段落说明新平台级评测路由与移除的旧路由；验证：文档中的路径与代码路由一致（人工核对 `routes/`）。

## 5. 前端

- [x] 5.1 在 `frontend/src/components/AppLayout.tsx` 增加「评测」「看板」顶层导航，`App.tsx` 增加 `/evals`、`/scores` 路由；验证：前端导航渲染测试/手动进入两页可打开。
- [x] 5.2 移除 `KnowledgeBaseDetail.tsx` 的 `evals`、`scores` tab 及 `App.tsx` 对应子路由，旧深链兜底重定向到 `documents`；验证：访问 `/kbs/:id/evals` 落到文档页。
- [x] 5.3 新建评测页：题集列表/创建/编辑 cases/删除（创建者可见编辑），运行时多选有 editor 权限的库；验证：`cd frontend && npm test` 与手动跑通一次多库运行。
- [x] 5.4 新建看板页：按题集展示趋势、跨库对比，仅展示可访问库；验证：不同成员登录只看到自己的库。
- [x] 5.5 更新 `frontend/src/services/api.ts`：新评测接口签名（题集 CRUD、批量运行、runs、trend、overview），删除旧 scoped 调用；验证：`npm run build` 通过且无类型错误。

## 6. 集成验证

- [x] 6.1 后端整体 `make check`（lint + typecheck + test）通过。
- [x] 6.2 前端 `cd frontend && npm test && npm run build` 通过。
- [x] 6.3 端到端手测：新建题集→对两个库批量运行→看板可见跨库对比→非成员看不到该库结果；验证：按上述步骤实际执行并记录结果。

## Workflow follow-up

- 实现完成并通过项目评审后，用 `/opsx-archive` 归档本变更。
- 归档后核验 `knowledge-evaluation`、`knowledge-storage`、`knowledge-base-registry`、`knowledge-base-access-control` 主 spec 已更新。
