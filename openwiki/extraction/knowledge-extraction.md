---
type: concept
title: AI 知识提取流水线
description: 导入的源文档如何经 LLM 提取为业务知识：harness 的结构化约束、稳定概念 id、claim 级来源与增量合并、写盘前校验，以及可替换的 LLM 客户端与离线 FakeLLM。
tags: [extraction, llm, harness, claims, pipeline, provenance]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-9c83888bdb8270e778f949ed
    resource: repo://mykb/extraction/code_ref.py
  - id: openwiki-source-70832f0dba3eb1ab3fd9ad28
    resource: repo://mykb/extraction/harness.py
  - id: openwiki-source-517841b0b61634ad40620877
    resource: repo://mykb/extraction/llm.py
  - id: openwiki-source-4ccdf13c8842742626ab4110
    resource: repo://mykb/extraction/pipeline.py
  - id: openwiki-source-5bf5447fc72bad3022b28450
    resource: repo://mykb/extraction/staging.py
  - id: openwiki-source-7dc8f0150acafc9ffaffbc8c
    resource: repo://tests/test_extraction_pipeline.py
  - id: openwiki-source-02a88f838799ec6965ae776e
    resource: repo://tests/test_extraction.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# AI 知识提取流水线

导入的源文档不会直接变成业务知识。它们先进入按知识库串行的提取队列，由提取 worker 读取 raw 概念，调用 LLM 产出结构化结果，再经 harness 约束成合法的 OKF 业务知识概念，最后在一条独立分支上生成文档级评审 MR。`knowledge/` 完全由 AI 撰写，人只做评审。本文聚焦“单份文档如何被提取成知识”。

## 组件与职责

| 模块 | 职责 |
| --- | --- |
| `extraction/pipeline.py` | 单飞调度、分支构建、审批/拒绝/重做 |
| `extraction/queue.py` | 待审队列与状态机 |
| `extraction/drafter.py` | 读取源概念、调用 LLM、产出概念 |
| `extraction/harness.py` | 结构化归一、构建概念、写盘前校验、幂等合并 |
| `extraction/llm.py` | LLM 客户端抽象与默认实现 |
| `extraction/staging.py` | 待审内容的文件暂存（仓库外） |
| `extraction/lineage.py` | 构建 sources 条目、追踪依赖 |
| `extraction/code_ref.py` | 代码引用型源概念（不复制代码本体） |

## 单份文档的提取流程

`process_pending` 是入口，按知识库加锁并循环推进队列（`mykb/extraction/pipeline.py:145`）：

1. 若 `MYKB_EXTRACTION_ENABLED` 关闭则直接返回。
2. 若该库已有打开中的 MR（`processing/queued-for-review/reviewing`），停止，保证**同一库一次只推进一份文档**。
3. `claim_next` 取队首项并置 `processing`；若其导入任务已取消，清理暂存并标记 `rejected` 继续。
4. 构建分支 `change/doc-<slug>-<id前8位>`，基线为 `main`。
5. 处理该项：删除动作走 `_delete_and_revise`；新增/修改则加载暂存概念、写入 raw、提取受影响知识。
6. `commit_all` 后若分支相对 `main` 有变更则留在分支等待评审，否则删分支并标记 `merged`。
7. 标记 `reviewing` 并把状态写回，返回该项 id；一次调用只产出一个 MR。

若构建过程抛异常，`_recover_to_main` 会强制回到 `main` 并 `reset --hard`，把该项标记 `failed` 后继续处理后续队列，避免一份坏文档卡死整库（`mykb/extraction/pipeline.py:188`）。

## 受影响的业务知识

文档不是孤立地生成新页面，而是先确定“受影响的已有知识”：

- `_affected_knowledge` 用 `trace_affected` 做传递闭包：从该源 id 出发，沿 `sources` 边找直接和间接依赖的业务知识；再次扫描 `source_ids()` 与 claim 级 `sources` 补充（`mykb/extraction/pipeline.py:51`）。
- 若存在受影响知识，对每个受影响的页面保留其标题和来源（融合型页面沿用多个来源），重新提议内容并把 `status` 置为 `draft` 后再校验写回（`mykb/extraction/pipeline.py:62`）。
- 若没有受影响知识，则新建一条业务知识，路径由 `stable_relative_path(标题)` 派生为 `topics/<slug>`（`mykb/extraction/pipeline.py:86`）。

## harness：把 LLM 输出约束成合法概念

`Drafter.propose_concept` 读取源概念正文，调用 `llm.extract`，再经 `normalize_output` 强制成固定形状（`mykb/extraction/drafter.py:62`）。`normalize_output` 只接受字典，规整 `title`、`summary`、`tags`、`claims`（每条含 `text` 与非空校验）、`conflicts`、`open_questions`（`mykb/extraction/harness.py:49`）。

`build_concept` 把结构化输出转成 OKF 概念（`mykb/extraction/harness.py:116`）：

- `type` 固定为 `业务知识`，`status` 为 `draft`，`generated.by` 为 `ai:<model>`；
- `sources` 聚合所有来源 id 并附 `resource`/`title` 元数据；
- `claims` 原样保留，形成 **claim 级来源**；
- `x-extraction` 记录模型、prompt 版本、源 hash 与任务 id；
- 冲突与待解问题写入 `x-conflicts`/`x-open-questions`；
- 正文由 `render_body` 渲染，当前输出固定包含 `# 标题`、摘要与一个 `## 要点` 小节。

`harness.py` 中声明了按知识类型的模板表 `KNOWLEDGE_TEMPLATES`（业务知识/术语/流程/规则/指标），但当前实际渲染只使用统一的 `要点` 小节；模板表尚未在写盘路径中强制执行。以源码为准，不要假设这些模板会改变输出结构。

### 稳定概念 id

新建知识的目标路径来自标题的确定性 slug（`stable_relative_path` → `topics/<slugify(标题)>`），因此相同主题会落到同一路径，而不是每份文档各生成一个随机页面（`mykb/extraction/harness.py:44`）。这使得重复导入可以命中同一概念并走幂等合并。

### 写盘前校验

`validate_concept` 在写盘前返回问题列表，空列表表示通过（`mykb/extraction/harness.py:168`）：

- `type` 必须是 `业务知识`，`title` 非空；
- 至少有一条 claim，且每条 claim 至少引用一个来源；
- claim 引用的来源必须存在于允许集合或当前 `raw/` 概念中（防止引用不存在的来源）；
- 正文中指向 `.md` 的本地相对链接必须实际存在（断链检查）；
- 若指定了 `target_id`，不能与其它业务知识页面存在重复标题。

任一问题都会抛 `ExtractionValidationError`，该文档被标记 `failed` 而不是写入半成品。

### 幂等合并

`apply_concept` 在目标文件已存在时比较 `semantic_signature`（标题、tags、claims（含来源）与正文，忽略时间戳与模型），完全相同则视为未变更、不重写；否则覆盖（`mykb/extraction/harness.py:202`）。签名函数刻意排除易变元数据，使相同内容重提不会制造无意义 diff（`mykb/extraction/harness.py:156`）。

## LLM 客户端

`get_default_llm` 依据环境变量返回实现（`mykb/extraction/llm.py:141`）：

- 配置了 `MYKB_LLM_BASE_URL` 与 `MYKB_LLM_API_KEY` 时返回 `OpenAICompatibleLLM`，模型取自 `MYKB_LLM_MODEL`（默认 `gpt-4o-mini`）。它向 `{base_url}/chat/completions` 发请求，提取时要求 `response_format={"type":"json_object"}` 并注入 JSON schema 提示，解析失败抛 `LLMError`（`mykb/extraction/llm.py:101`）。
- 否则返回 `FakeLLM`，这是确定性、离线的实现，按源首行生成标题与摘要、每源一条 claim，便于无凭证测试（`mykb/extraction/llm.py:34`）。

## 暂存与代码引用

- 待审内容暂存在仓库外的 `MYKB_KB_ROOT/.pending/<item_id>`，因此不会出现在 git 状态或被打进提交（`mykb/extraction/staging.py:1`）。概念与资产分别在 `concept.md` 与 `assets/`。
- 代码不复制进 bundle：`create_code_source` 生成 `type: 代码` 的引用型 raw 概念，`resource` 指向代码文件、正文只放摘要（`mykb/extraction/code_ref.py:23`）。从代码提取的业务知识会保留该 `resource`。

## 安全与失败语义

- LLM 只被允许依据源数据陈述，prompt 明确禁止臆造；claim 必须标注来源 id。
- 校验失败、LLM 错误或写盘异常都会让该文档 `failed`，不写半成品，也不阻塞后续队列。
- 提取被 `MYKB_EXTRACTION_ENABLED=false` 全局关闭时可整体停用。

## 代表测试

`tests/test_extraction.py` 覆盖 AI 草稿的 lineage、写入 knowledge、验证标记与 code source 仅引用；`tests/test_extraction_pipeline.py` 覆盖导入→评审→审批流程、重导幂等跳过、删除文档修订知识、harness 校验与幂等 apply、修改重导生成 modify MR、拒绝/重做以及队列状态机与恢复。
