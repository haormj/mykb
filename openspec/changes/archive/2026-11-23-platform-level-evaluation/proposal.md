# Proposal

## Why

评测集与评测运行当前作为知识库 git 仓库的一部分（`evals/` 层级与 `.mykb/eval-runs/`）存放，并被封装成每个知识库详情里的「评测 / 看板」tab（源自此前的 `scope-features-to-knowledge-base`）。这混淆了两类本质不同的数据：知识库 git 仓库应当是**纯知识内容**（源数据与业务知识），而评测是对知识质量的度量，属于平台运营数据。把评测塞进仓库还使题集无法复用，也无法横向比较多个知识库。

## What Changes

- 评测集与评测运行从知识库 git 仓库迁到 **Postgres 平台元数据**，知识库仓库只保留 `raw/`、`knowledge/` 两层。**BREAKING**：OKF 布局去掉 `evals` 层级。
- 评测集成为**平台级共享资源**：不属于任何单一知识库，创建者拥有（他人可读可运行），同一题集可对多个知识库复用。
- 一次评测运行**绑定一个目标知识库**并记录其知识版本；界面支持选择多个（有权限的）目标库批量运行，产生多条运行。
- 权限：运行评测需对目标库具备 `editor`；运行结果仅对目标库成员（`viewer` 及以上）与平台管理员可见，保留库级隔离。
- 知识质量（A）分采用**固定分母严格口径**：缺概念记 0，并按 `hit / not_retrieved / unverified / missing` 四类拆解，另报覆盖率；无 `expected_concept` 的题只计入端到端（B）分。
- 前端：「评测」「看板」从知识库详情 tab 提升为**顶层导航**；知识库详情只保留文档、知识、审核、设置。看板按用户可见库范围展示，并支持同题集跨库对比。
- 现有开发期 `evals/*.md` 与 `.mykb/eval-runs/` 数据**不迁移**，直接弃用。

## Capabilities

### New Capabilities

<!-- 无新增能力：评测集管理与运行并入既有 knowledge-evaluation，前端导航属 UI 不作为 spec。 -->

### Modified Capabilities

- `knowledge-evaluation`：评测集改为平台级共享资源、运行绑定目标库、结果库级可见、A 分改为固定分母严格口径并附覆盖率与四类拆解、平台级看板与跨库对比；删除「评测归属知识库」。
- `knowledge-storage`：知识分层由 raw/knowledge/evals 改为仅 raw 与 knowledge。
- `knowledge-base-registry`：新建知识库的 OKF 布局去掉 `evals` 层级。
- `knowledge-base-access-control`：明确运行评测按目标库角色校验、结果可见性按目标库成员约束、评测集管理按创建者所有权而非库角色。

## Impact

- **Backend**: 新增 Postgres 表（`eval_sets` / `eval_cases` / `eval_runs` / `eval_case_results`）及 Alembic 迁移；`mykb/evaluation/*` 改为读写数据库而非 bundle；`mykb/api/routes/evaluation.py` 从 `/kbs/{kb_id}/eval/*` 改为平台级路由并带目标库参数。
- **Storage/OKF**: `mykb/okf/bundle.py` 的 `LEVELS` 去掉 `evals`；新建知识库不再建 `evals/` 目录。
- **Frontend**: 顶层导航新增「评测」「看板」；移除知识库详情 `evals` / `scores` tab；新增评测集管理与选库运行页、跨库看板。
- **Specs**: `knowledge-evaluation`、`knowledge-storage`、`knowledge-base-registry`、`knowledge-base-access-control` 四个 delta。
- **Data**: 开发期评测数据不迁移；无生产数据。
