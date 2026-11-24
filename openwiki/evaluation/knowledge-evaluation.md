---
type: concept
title: 知识评测与看板
description: mykb 平台级评测集的设计、单库与跨库运行、A 知识质量分与 B 端到端分的计算口径、逐题结果快照、结果可见性以及趋势与看板聚合。
tags: [evaluation, metrics, benchmarking, scoring, dashboard]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-7682159af48c7c129cb11254
    resource: repo://mykb/api/routes/evaluation.py
  - id: openwiki-source-d8b2da3595d5b74f842650ba
    resource: repo://mykb/db/models.py
  - id: openwiki-source-0af9404c7a7014b13f64486d
    resource: repo://mykb/evaluation/runner.py
  - id: openwiki-source-0e9c3fe0f814eadcc61193ff
    resource: repo://mykb/evaluation/store.py
  - id: openwiki-source-91b7abc42435b1f506aa28fe
    resource: repo://mykb/evaluation/types.py
  - id: openwiki-source-c60faaa8fff57df6c1fdc61f
    resource: repo://tests/test_evaluation.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 知识评测与看板

评测用于衡量“知识本身覆盖得怎样（A）”和“端到端问答质量如何（B）”。它是**平台级共享资源**：评测集不隶属于任何知识库、不进入 git bundle，而是存于 Postgres；一次运行绑定一个目标库，同一题集可对多个目标库批量运行以做跨库对比。这一定位在 `mykb/evaluation/store.py` 与路由模块的注释中明确说明。

## 数据与作用域

- 评测集 `eval_sets` 由单一用户拥有，包含有序的 `eval_cases`（`question`、`reference_answer`、可选 `expected_concept`/`domain`/`difficulty`），见 [平台数据模型](../architecture/data-model.md)。
- 一次运行 `eval_runs` 绑定 `set_id` + `target_kb_id`，记录 `knowledge_version`、`case_count`、`coverage`、`a_score`、`b_score`。
- 逐题结果 `eval_case_results` **快照化**了当时的 `question`，因此日后编辑题集不会改变历史运行的含义（`mykb/db/models.py:266`）。

评测集的读权限较开放（登录用户都能列出/查看），但修改与删除只有创建者或平台管理员可做，否则 403；运行结果只对目标知识库成员和平台管理员可见（`mykb/api/routes/evaluation.py:133`）。

## 运行器：纯打分

`EvalRunner` 是纯打分组件：它接收题目数据、目标库的 `Bundle` 和检索服务，不碰数据库、不写任何评测存储（`mykb/evaluation/runner.py:1`）。持久化完全由 `mykb/evaluation/store.py` 负责，便于离线测试。

对每道题执行两步：

### A：知识质量分

`_score_knowledge` 按固定顺序分类，返回 `(status, a_score)`（`mykb/evaluation/runner.py:77`）：

1. 无 `expected_concept` → `b_only`（不参与 A 分）；
2. 概念文件不存在 → `missing`；
3. 概念存在但不是 `verified && stable` → `unverified`；
4. 检索 top_k 命中包含期望概念 → `hit`（1.0）；
5. 否则 → `not_retrieved`。

只有 `hit` 得 1 分，其余（`missing`/`unverified`/`not_retrieved`）为 0。

### B：端到端分

`_score_e2e` 走完整“问题 → 检索 → 生成 → 回答”链路，把答案与 `reference_answer` 用**词集合 F1 相似度**比较（`mykb/evaluation/runner.py:15`、`mykb/evaluation/runner.py:90`）。相似度基于 `retrieval.engines.markdown_rag.tokens` 分词，确定性且离线，不依赖外部模型。

### 聚合

`run` 计算（`mykb/evaluation/runner.py:54`）：

- `a_score`：所有非 `b_only` 题目的平均 A 分；没有此类题目时为 0；
- `coverage`：非 `b_only` 题目中状态属于 `{hit, not_retrieved, unverified}` 的比例，即“知识存在但未必被召回/审核”的覆盖范围；
- `b_score`：全部题目的平均 B 分；
- `knowledge_version`：取自检索服务的 engines 版本（通常是快照的 git commit）。

## 状态语义

`mykb/evaluation/types.py` 定义了五种逐题状态：

| 状态 | 含义 | 计入 coverage | A 分 |
| --- | --- | --- | --- |
| `hit` | 期望概念已审核且被检索命中 | 是 | 1.0 |
| `not_retrieved` | 期望概念已审核但未被召回 | 是 | 0 |
| `unverified` | 期望概念存在但未审核/不稳定 | 是 | 0 |
| `missing` | 期望概念不存在 | 否 | 0 |
| `b_only` | 题目没有期望概念 | 否 | 不计入 A |

`b_only` 被刻意排除在 A 分与 coverage 之外，因为这类题只衡量端到端回答，不代表知识覆盖。测试 `test_b_only_cases_do_not_lower_a_score` 固定了这一行为。

## 运行与批量语义

`POST /eval/sets/{set_id}/run` 接受 `target_kb_ids`（去重后处理，空则 400）（`mykb/api/routes/evaluation.py:216`）：

1. 先对所有目标库以 `editor` 权限逐一 `ensure_kb_role` 预检；
2. 任一目标鉴权失败即抛 403，`runs` 一条都不会写入——这是“全有或全无”的批量语义；
3. 全部通过后，对每个目标库用其检索缓存构建服务运行，并 `save_run` 落库。

测试 `test_api_batch_run_is_all_or_nothing` 验证了失败时不会产生任何运行记录。

## 查询、趋势与看板

- `GET /eval/runs?kb_id=&set_id=`：带 `kb_id` 时校验该库 viewer 权限后按库过滤；不带 `kb_id` 时聚合当前用户可访问知识库范围内的运行（`mykb/api/routes/evaluation.py:254`）。
- `GET /eval/runs/{run_id}`：先按目标库 viewer 鉴权，再返回运行汇总与逐题结果。
- `GET /eval/sets/{set_id}/trend?kb_id=`：按时间升序返回某题集在某库上的运行点（`mykb/evaluation/store.py` 的 `trend`），用于趋势图。
- `GET /eval/overview`：返回可见库、全部评测集和可见运行的聚合，供看板做同题集跨库对比（`mykb/api/routes/evaluation.py:315`）。

## 前端呈现

前端「知识评测」一级菜单包含看板（`/scores`）和评测集（`/evals`）两个页面，使用 recharts 画趋势/对比图，并允许管理评测集、选择一个或多个目标库运行。详见 [前端应用](../frontend/web-application.md)。

## 代表测试

- `tests/test_evaluation.py`：分类五态、`b_only` 不影响 A 分、相似度边界、评测集 CRUD 的 owner-only、批量运行与结果可见性、overview 的跨库与隔离、批量运行全有或全无。
- `tests/test_evaluation_store.py`：store 层的评测集 CRUD、跨库运行记录与趋势数据。
