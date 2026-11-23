# Design

## Context

见 `proposal.md`。要点约束来自现有实现：

- 每个知识库是一个 git 仓库承载 OKF bundle（`raw/`、`knowledge/`、`evals/`），见 `mykb/okf/bundle.py`。
- 导入已生产化：`ImportTask` 持久化、进程内执行器、按 KB 串行锁、转换后 `gitops.commit_all` 直接提交到 `main`（`mykb/importing/service.py`）。
- 提取零件已存在但无调用方：`Drafter.draft(source_ids)` 融合成一条概念（`mykb/extraction/drafter.py`）、`GitReview` 以分支/合并做逐概念审核（`mykb/extraction/review.py`）、`trace_affected` 算传递影响面（`mykb/maintenance/lineage_trace.py`）。
- 检索只索引 `verified && stable`（`mykb/retrieval/index.py`），这条门禁保持不变。
- 服务以单进程运行（执行器进程内），提取同样复用该约束。

## Goals / Non-Goals

**Goals:**

- raw 变更（增/改/删）自动触发提取，产出经人工评审合并后才进主干与检索。
- 以"一个源文档 = 一个文档级 MR"为评审单元，MR 同时含该文档 raw 与受影响知识，串行生成避免融合页冲突。
- `knowledge/` 完全由 AI 撰写，用 schema + 模板 + 校验约束 LLM，稳定可复现。
- claim 级血缘支撑精确的变更/删除修订。
- 为将来自动合并埋好评估信号（本期不消费）。

**Non-Goals:**

- 自动合并（无人审入主干）。
- 跨知识库共享 / 融合。
- 向量化/模型级提取质量评分。
- 由外部同步源"消失"驱动的隐式删除（v1 仅显式删除）。

## Decisions

### 1. 导入与提取解耦，用持久化待审队列

导入任务完成"转换"后不再直接提交 `main`，而是把文档写入按 KB 的**待审队列**；一个单飞 worker 逐篇推进。队列用数据库表持久化（与 `ImportTask` 同库），重启可恢复。

- 备选：内存队列 —— 重启丢失、无法跨进程，否决。
- 备选：导入任务内直接同步提取 —— 导入被 LLM 长耗时阻塞、失败重试粒度差，否决。

### 2. 文档级 MR + 严格串行

一文档一分支 `change/doc-<slug>`，内容 = 该文档 raw 概念 + `trace_affected(raw_id)` 的业务知识变更。**MR N 合并后才基于最新主干生成 N+1**（单飞），避免同一融合页被多个开着的 MR 同时改。

- 备选：一次导入一个批量 MR —— 冷启动/大批量不可审。
- 备选：并行生成多个文档 MR —— 共享融合页必冲突、需反复 rebase 重提取，否决。

```
导入 -> 转换 -> 入待审队列(raw 暂存，不进 main)
  worker(按 KB 单飞):
    取队首 doc
      -> 以最新 main 为基准提取(harness) -> validate
      -> 分支 change/doc-<slug>(raw + 受影响页)
      -> 等人工 merge -> main 前进 -> 下一 doc
```

### 3. raw 进 MR，主干恒为"已审"

raw 也纳入同一 MR 评审（转换质量也需人看）。因此 `main` 只含已合并内容，删除/改写 `importing` 里"转换即 commit 到 main"的收尾。`GitReview` 从"逐概念分支"泛化为"一个分支装整批文件（raw + knowledge）等待合并"。

### 4. 提取 harness：模板 + schema + 稳定身份 + 幂等合并

- **结构化输出**：LLM 返回 JSON（`title/summary/tags/claims[]/conflicts[]/open_questions[]`），平台渲染成 markdown 正文；frontmatter 由平台写入，不由模型自由生成。
- **类型模板**：`业务知识` 之外按类型（术语/流程/规则/指标）选模板与必填 section；未知类型回落通用模板。
- **稳定身份**：概念 id 由主题/实体键派生（slug 化），不由模型起名，确保重跑落同一路径。
- **幂等增量合并**：按 claim 比对现有页，只改动受影响 claim（patch），语义无变化则不写盘。
- **写盘前校验**：schema 合规、每条 claim 的 `sources` 指向真实存在的 raw 概念、无重复实体键、无断链；失败则不落盘并记录原因。
- **可复现**：pin `model`、`prompt_version`、`temperature`（沿用 `MYKB_LLM_*`，新增提示词版本常量），写入 `x-extraction`。

- 备选：让模型直接产出整页 markdown —— 输出不稳定、diff 噪音大、无法做 claim 级修订，否决。

### 5. claim 级来源，但签发状态停在页级

`claims[]` 每条带 `sources`（raw 概念 id）。`verified/stable` 仍按概念记录，检索、回滚、过期继续按概念粒度。将来若需 claim 独立签发，再以 `x-claims[].verified` 增量扩展，不在本期下沉。

- 理由：把 `verified` 下沉到 claim 会牵连 `index`、`rollback`、`staleness`、`lineage`、OKF 模型五处，成本过大；当前 claim 血缘已足够支撑删除/修改修订与忠实度评审。

### 6. 变更检测与删除修订

- raw 概念在 frontmatter 记录内容指纹（复用已有 `x-original-sha256`）。重新导入时比对指纹判断"实质变更"，避免仅时间戳导致误判。
- 删除：`v1` 仅支持显式删除。删除文档时按 `trace_affected` + claim 血缘逐个处理相关断言（移除唯一证据断言 / 摘除多余引用 / 标记无来源 / 证据塌陷则 needs-review 或提议删页），所有修订纳入该文档 MR。

### 7. 评审接口与部分接受

review 从"逐概念 approve"改为"按文档级 MR 审批"：

- 列出待审 MR（含变更文件集、受影响页、校验结果）。
- 查看整批 diff，可按文档聚焦、内联展示 claim→sources。
- 合并 = 把分支合入主干并为通过的业务知识盖 `verified`、置 `stable`。
- 部分接受 = raw 合入、指定业务知识退回，触发对该文档知识重提取并更新同一 MR。
- 拒绝 = 丢弃分支（含 raw），或保留 raw 仅退知识。

### 8. 任务状态与信号

`ImportTask` 状态扩展为 `converting | queued-for-review | reviewing | merged | rejected | failed | cancelled`；保留 `partial` 语义用于转换层。提取产生 `x-extraction`（model、prompt_version、source_hash、task）与评审决定记录，作为未来自动合并的判据。

## Risks / Trade-offs

- [单飞导致冷启动慢] → 接受，质量优先；将来可对低风险批量加"自动合并/批量评审"分流。
- [LLM 非确定性导致 diff 抖动] → 稳定身份 + 幂等合并 + pinned 版本 + 语义无变化不写盘。
- [融合使单文档 MR 触及多页，评审体量不均] → MR 按文档聚焦、内联证据；高扇出文档单独提示。
- [统一 MR 把 raw 与 knowledge 绑定] → 提供"接受 raw、退回知识"的部分接受。
- [进程内单飞 worker] → 与现有执行器一致，维持 `--workers 1`；多实例需外部队列（记为后续工作）。
- [删除语义危险] → 仅显式删除 + 必须经同一 MR 人工确认 + 提议删除而非自动删页。
- [旧数据兼容] → 已有 raw 已在主干，新流程只作用于新变更；旧草稿可走新评审或忽略。

## Migration Plan

1. 新增待审队列表与任务状态值（Alembic 迁移），保留旧状态读取。
2. 导入收尾从"提交到 main"改为"入队 + 生成候选变更"，通过特性开关灰度。
3. 新旧评审并存一个周期：旧逐概念 approve 保留到新文档级 MR 评审可用了再下线。
4. 回滚：每个文档 MR 在独立分支，丢弃分支即回滚，不影响主干；整体回退用特性开关切回旧导入收尾。
5. 上线顺序：harness/校验 → 队列与单飞 worker → 文档级 MR 评审 → 删除修订 → 页级体检。
