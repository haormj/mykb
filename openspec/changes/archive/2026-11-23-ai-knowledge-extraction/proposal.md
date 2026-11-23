# Proposal

## Why

导入目前只完成"文档转 markdown"（写入 `raw/`），并没有把源数据变成可检索的业务知识；现有的提取零件（`Drafter`、`GitReview`、血缘）没有任何调用方，导入结束后不会触发提取。知识质量是平台的核心价值，而当前缺少"LLM 产出 + 人工把关 + 可追溯 + 可持续维护"的完整闭环。现在补上这一步：让每个知识库的 raw 变更自动触发提取，产出经人工评审后才进入主干与检索。

## What Changes

- 导入产物不再直接提交到 `main`，而是进入**按知识库串行、待审的文档队列**；raw 与提取结果一起构成一个**文档级评审 MR**。
- raw 的新增 / 修改 / 删除自动触发提取；删除不是简单删页，而是按 **claim 级血缘**修订所有受影响知识。
- `knowledge/` 层完全由 AI 撰写，人不直接改正文，只做"忠实度 + 转换质量"评审与合入。
- 引入约束框架（harness）：知识类型模板 + JSON schema（模型只填槽）、稳定身份（id 由实体/主题派生）、`claim -> sources` 血缘、幂等增量合并、写盘前 `validate`、pinned model/prompt。
- **严格串行**：MR N 合并后，才针对最新 `main` 生成 N+1，消除共享融合页的 MR 冲突。
- `main` 恒为"已审"状态；仍只有 `verified && stable` 进入检索引擎（沿用现有门禁）。
- 记录未来评估信号（claim 血缘、validate 结果、人审决定与理由码、model/prompt 版本、扇出度），为将来引入自动合并留依据——**本期不做自动合并**。
- 导入任务生命周期扩展为 `converting -> queued-for-review -> reviewing -> merged | rejected`。
- 增加周期性**页级体检**（schema / 重复实体 / 断链 / 冲突），弥补"逐文档 delta 视角"看不到整页累积自洽的盲区。

非目标（本期不做）：自动合并（无人审入 main）、跨知识库共享/融合、多引擎提取对比、向量化提取质量评分。

## Capabilities

### New Capabilities

- 无。本变更复用现有能力边界，不引入新 capability。

### Modified Capabilities

- `knowledge-extraction`: 重写为"raw 变更自动触发 → AI 独占撰写 → 文档级 MR → 严格串行 → claim 级血缘 → 人审晋升 stable"的完整提取闭环。
- `knowledge-import`: raw 不再直接落 `main`，改为进入按 KB 串行的待审队列，并随提取结果组成文档级 MR；任务生命周期延伸到合并。
- `knowledge-maintenance`: 由 raw 变更驱动重提取；删除文档时按 claim 级血缘修订受影响知识，而非整页删除。
- `knowledge-storage`: 增加 claim 级来源（`claims[].sources`）、提取元数据（`x-extraction`）以及"`main` 恒为已审"的存储不变量。

## Impact

- 代码：
  - `mykb/extraction/`：重写 drafter / review，新增 harness（类型模板、schema 校验）、提取调度与队列。
  - `mykb/importing/`：导入不再直接 `commit_all` 到 `main`，改为产出待审草稿并进入队列。
  - `mykb/api/routes/review.py`、`import_tasks.py`、`documents.py`：评审从逐概念审批改为文档级 MR 审批；导入任务语义调整。
  - `mykb/db/models.py`：任务状态与待审队列。
  - `mykb/maintenance/`：变更检测与删除修订接入。
- API：导入任务语义变化；review 接口从逐概念 approve 改为文档级 MR；新增提取调度/队列相关接口。
- 数据：`knowledge/` 概念 frontmatter 增加 claim 级 `sources` 与 `x-extraction`；`raw/` 概念补充内容指纹用于变更检测。
- 不受影响：检索门禁（仍仅 `verified && stable`）、OKF 合规校验、多知识库隔离、Git LFS 资产存储。
