# Design

## Context

See `proposal.md - Why`. Constraints from the current implementation:

- 平台元数据用 SQLAlchemy + Alembic 管理（`mykb/db/models.py`、`migrations/versions/000{1,2,3}_*.py`）；内容存于每个知识库的 git 仓库。
- 评测当前完全绑定 bundle：`EvalSetManager` 读写 OKF `evals/` 概念（`mykb/evaluation/evalset.py`），`Scoreboard` 写 `.mykb/eval-runs/`（`mykb/evaluation/scoreboard.py`），`EvalRunner` 直接读 bundle 概念（`mykb/evaluation/runner.py`）。
- API 前缀 `/kbs/{kb_id}/eval`，权限用 `require_kb_role(...)`（`mykb/api/deps.py`），平台管理员自动放行。
- 运行评测依赖 `request.app.state.retrieval_cache`（`bundle_for(kb)` + `cache.get(kb)`），`knowledge_version` 取自检索索引的 `version`。
- 业务知识概念 id 由主题稳定派生为 `knowledge/topics/<slug>`（`mykb/extraction/harness.py`），同一主题在不同库可能解析到同一 id，这是跨库 A 分可行的前提。
- 前端 React Router + antd：`App.tsx` 路由、`AppLayout.tsx` 侧边栏、`KnowledgeBaseDetail.tsx` 详情 tab、`services/api.ts` 客户端。

## Goals / Non-Goals

**Goals:**
- 评测集/运行迁到 Postgres，成为平台级共享资源，KB bundle 只含 raw/knowledge。
- 一次运行绑定一个目标库；批量运行按库分别落记录；结果按目标库成员可见。
- A 分改为固定分母严格口径（C1）+ 覆盖率 + 四类拆解；B 分算法不变。
- 「评测」「看板」提升为顶层导航，支持同题集跨库对比。

**Non-Goals:**
- 不改端到端（B）分的相似度算法与生成链路。
- 不做题集版本化/fork/导入导出、不做定时批量评测调度。
- 不迁移开发期评测数据。
- 不引入新的评分模型或向量化评分。

## Decisions

### 1. Postgres 表结构

```
eval_sets(id, owner_user_id FK->users, name, title, description,
          created_at, updated_at)                       -- 全局，无 kb_id
eval_cases(id, set_id FK->eval_sets ON DELETE CASCADE,
           position, question, reference_answer,
           expected_concept NULL, domain NULL, difficulty NULL)
eval_runs(id, set_id FK->eval_sets, target_kb_id FK->knowledge_bases,
          triggered_by FK->users, knowledge_version NULL,
          case_count, coverage, a_score, b_score, created_at)
eval_case_results(id, run_id FK->eval_runs ON DELETE CASCADE,
                  case_id FK->eval_cases ON DELETE SET NULL,
                  question, expected_concept NULL,
                  status, a_score, b_answer, b_score)
```

- `eval_sets` 无 `kb_id`；跨库关联只发生在 `eval_runs.target_kb_id`。
- `eval_case_results` 冗余快照 `question`/`expected_concept`：题集后续被编辑不影响历史运行的解读，趋势稳定。
- 备选：题目整体存 `eval_sets` 的一个 JSON 列 + 运行时快照整份 JSON。放弃——单题编辑/查询要走整列读写，且 `eval_case_results` 仍要拆开才能算分类统计。
- 备选：`eval_case_results` 只存 `case_id` 靠 join 取题面。放弃——题集被改后历史分数含义变化，趋势不可比。

### 2. 评分口径（C1）

`EvalRunner` 从"读 bundle 概念"改为"接收 DB 题集 + 检索服务"。逐题分类顺序：

```
missing        bundle 无 expected_concept            -> status=missing,        a=0
unverified     存在但非 verified/stable              -> status=unverified,     a=0
not_retrieved  存在且 stable 但 top_k 未命中          -> status=not_retrieved,  a=0
hit            命中                                  -> status=hit,            a=1
b_only         题无 expected_concept                 -> status=b_only，只算 B 分
```

- A 分分母 = 带 `expected_concept` 的题数（固定，跨库可比）。
- `coverage` = `(hit + not_retrieved + unverified) / 带概念题数`，即"该库是否存在期望概念"，作为诊断列。
- `b_only` 题（含 `expected_concept` 为空）不进 A 分分母，只进 B 分——修正现在"空概念返回 0 拉低 A 分"的问题。
- 逐步检查顺序固定为 missing → unverified → not_retrieved → hit，保证分类互斥可复现。

### 3. 授权

- 题集 CRUD：按 `owner_user_id`——创建者改/删，其他登录用户只读、可运行。
- 运行：对每个 `target_kb_id` 复用 `require_kb_role("editor")` 的判定逻辑。为支持一次多库，把 `deps.py` 里 membership+rank 判定抽成 `ensure_kb_role(session, user, kb_id, min_role) -> KbAccess`，依赖工厂 `require_kb_role` 与批量运行共用。
- 批量运行采取**全有或全无**的预校验：任一目标库不足 editor 则整请求 403，不产生任何运行。
- 结果查询/看板：`ensure_kb_role(..., "viewer")` 或平台管理员；看板只聚合可访问库。

### 4. API 形态（平台级）

```
POST   /eval/sets                         editor 无涉，按登录用户
GET    /eval/sets                         登录用户
GET|PATCH|DELETE /eval/sets/{id}          创建者
POST   /eval/sets/{id}/run                {target_kb_ids:[...]} 逐库 editor
GET    /eval/runs?kb_id=                  viewer（该库）
GET    /eval/runs/{id}                    viewer（该库）
GET    /eval/sets/{id}/trend?kb_id=       viewer（按库过滤）
GET    /eval/overview                     viewer 及以上，返回可访问库的聚合
```

- 旧的 `/kbs/{kb_id}/eval/*` 移除。前端 `services/api.ts` 的 `listEvalSets/createEvalSet/runEval/evalTrend` 改为新签名。
- `eval_trend` 现由 `Scoreboard` 读 `.mykb/eval-runs`；改为查 `eval_runs` 表，按 `created_at` 升序。

### 5. OKF 层级

- `mykb/okf/bundle.py` 的 `LEVELS` 改为 `("raw", "knowledge")`；`ensure_layout` 不再建 `evals/`。
- 已存在库里的遗留 `evals/` 目录保留但不读取（不阻塞、不报错）；不做自动删除，避免误删。
- `EvalSetManager`、`Scoreboard` 中依赖 `evals` 层的路径删除或改签名；`EvalRunner` 保留纯评分函数（`similarity` 等）供新流程调用。

### 6. 前端

- 顶层路由：`/evals`（题集管理 + 选库运行）、`/scores`（看板）。侧边栏 `AppLayout` 增加两项。
- `KnowledgeBaseDetail` 的 `allTabs` 去掉 `evals`、`scores`；`App.tsx` 删除 `/kbs/:kbId/evals`、`/kbs/:kbId/scores` 路由；旧深链跳回 `documents` 或提示迁移。
- 评测页：题集列表（创建/编辑 cases/删除，创建者可见编辑按钮）；运行时多选当前用户可编辑的库（来自 `/kbs` 列表 + `my_role`）。
- 看板页：按题集分组，KB 维度折线/表格对比，数据来自 `/eval/overview` 与 `/eval/sets/{id}/trend`。

## Risks / Trade-offs

- [批量运行部分库无权限] → 全有或全无预校验，整请求 403，避免产生半批运行。
- [历史结果随题集编辑漂移] → `eval_case_results` 存题面快照，运行不可变。
- [去掉 `evals` 层级影响既有代码/测试] → 先 grep `evals`、`EvalSetManager`、`Scoreboard` 调用点，逐一改；`tests/test_evaluation.py` 重写。
- [深链 `/kbs/:id/evals|scores` 失效] → 路由兜底重定向到 `documents`。
- [A 分跨库可比但可能"冤枉"覆盖窄的库] → 用 `coverage` 诊断列区分"覆盖缺口"与"检索失败"；不改固定分母（这是横向可比的前提）。
- [Alembic 新增多表] → 仅新增表、无可破坏性改动；回滚靠丢弃表。

## Migration Plan

1. Alembic `0004_evaluation_tables.py` 新增四张表（仅新增，不动既有表）。
2. 后端：新增 `mykb/evaluation/store.py`（DB 读写）与平台级路由；改 `EvalRunner` 输入；`LEVELS` 去 `evals`。
3. 前端：加顶层导航与页面、移除详情 tab、改 API 客户端。
4. 数据：开发期 `evals/*.md` 与 `.mykb/eval-runs/` 不迁移；新库不再创建 `evals/`。
5. 回滚：去掉新路由/页面，删四张表即可；不影响既有知识内容。
