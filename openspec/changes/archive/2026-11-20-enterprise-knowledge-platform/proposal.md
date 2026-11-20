# Proposal

## Why

业界 AI 知识库方案（WeKnora、OpenViking 等）只把数据「导入」进 RAG 引擎，缺少对企业真正有价值的「知识治理与业务知识积累」能力。企业落地时，散落在各平台（语雀、Confluence、飞书、Git、数据库、代码仓等）的数据需要被统一摄入、加工融合、沉淀为可追溯、可评测、可持续维护的业务知识资产——这才是核心能力。本平台以 git + OKF（Open Knowledge Format）为唯一事实源，构建一条覆盖「导入 → 提取 → 检索 → 测评 → 维测」的完整知识生命周期流水线。

## What Changes

- 建立以 git 仓库（OKF bundle）为唯一事实源的知识存储层：源数据与业务知识分层存放，`sources`/`generated`/`verified`/`status` 等字段承载血缘与生命周期。
- 新增可扩展的数据导入能力：连接器框架分「同步数据」与「转 markdown」两阶段，支持从多种外部平台摄入数据。
- 新增数据提取能力：AI 起草业务知识草稿，经 git PR 人工审核后 merge 即标记为 `verified`，形成「源数据 → 业务知识」的血缘链。
- 新增统一数据检索层：对外暴露稳定接口，屏蔽内部引擎（WeKnora 等 markdown RAG 引擎、codegraph 代码检索），仅索引已审核的业务知识，索引与 git commit 版本绑定。
- 新增知识测评能力：业务人员创建评测集（问题 + 期望答案 + 期望命中概念），在指定知识集上运行评测任务，分别产出「知识质量」与「端到端能力」两类分数并展示趋势。
- 新增知识维测能力：检测源数据过期/变更，沿血缘链回溯受影响的业务知识并标记重审，支持废弃（deprecated/superseded_by）与回滚。

## Capabilities

### New Capabilities

- `knowledge-storage`: 以 git 仓库承载 OKF bundle 作为知识唯一事实源，管理源数据与业务知识的分层结构、血缘、版本与生命周期元数据。
- `knowledge-import`: 通过可扩展连接器框架（同步 + 归一化两阶段）从外部数据源摄入数据并产出 OKF 源数据概念。
- `knowledge-extraction`: 将源数据加工融合为业务知识（AI 起草 + 人工审核），产出带血缘、可验证的业务知识概念。
- `knowledge-retrieval`: 对外提供统一检索接口，屏蔽内部多引擎（markdown RAG、codegraph）差异，将已审核业务知识版本化同步到检索引擎。
- `knowledge-evaluation`: 管理评测集并运行评测任务，产出知识质量与端到端能力两类分数及趋势。
- `knowledge-maintenance`: 检测知识过期与源数据变更，沿血缘定位受影响知识，支持重审、废弃与回滚。

### Modified Capabilities

<!-- 全新项目，无既有 capability 需要修改 -->

## Impact

- 全新系统，无既有代码、API 或依赖受影响。
- 引入外部依赖：OKF 格式规范（v0.3，MIT）、git 作为存储后端、下游 RAG 引擎（初期 WeKnora）与代码检索（codegraph）作为检索层可替换实现。
- 涉及 AI/LLM 能力：数据提取阶段的自动起草、测评阶段的 LLM-as-judge 评分。
