# Design

## Context

全新项目，无既有代码约束。目标系统是一个 git-native、OKF-native 的企业知识管理平台。动机与范围见 proposal.md，本设计只记录「如何实现」的技术决策。核心约束：以 git 仓库 + OKF（Open Knowledge Format v0.3）为唯一事实源，业务知识是唯一对外检索的资产，源数据仅作加工原料。

## Goals / Non-Goals

**Goals:**
- 用 git + OKF 承载完整知识生命周期（导入 → 提取 → 检索 → 测评 → 维测），血缘与版本可追溯。
- 检索层对外收敛为统一接口，内部引擎可替换、可对比。
- 评测产生「知识质量」与「端到端能力」两类分数，作为能力建设度量。

**Non-Goals:**
- 不实现自有 LLM；起草与评测的生成/判定全部调用外部模型。
- 不复制代码本体进 bundle；代码走只读引用 + codegraph。
- 首个版本不做多租户、权限与 SSO（接口预留，不在本 change 实现）。

## Decisions

### D0: 技术栈 = Python 后端 + TypeScript 前端

核心平台用 Python（FastAPI + asyncio），前端（评测集管理、审核 UI、分数看板）用 TypeScript（后续阶段）。连接器 SPI 先采用进程内 Python 插件，将来若需跨语言连接器再演进为进程外（独立程序/容器）。

**理由**：系统核心是 AI/LLM 密集（起草、LLM-as-judge、解析），Python 生态（LangChain/LlamaIndex/RAGAS/OpenAI SDK/Pydantic）最强；团队具备 Python + TypeScript 经验，无 Go 背景。git 操作直接调 git CLI 或 GitPython 足够；统一接口用 FastAPI 出 REST，MCP 走官方 Python SDK。**备选**：Go —— 否决（团队不熟、AI 生态最弱）；TypeScript 全栈 —— AI 生态弱于 Python，保留作前端语言。

### D1: 唯一事实源 = git 仓库 + OKF bundle（而非数据库/专有存储）

以单个 git 仓库承载一个 OKF bundle，目录分层如下：

```
bundle/
├── index.md                 # bundle 元数据: okf_version, title, description
├── log.md                   # 更新历史
├── raw/                     # 源数据概念 (generated: process:<connector>, draft)
├── knowledge/               # 业务知识概念 (verified: human, stable)
└── evals/                   # 评测集概念 (question + reference_answer + expected_concept)
```

**理由**：OKF 的 `sources`/`generated`/`verified`/`status`/`stale_after`/`superseded_by` 字段直接承载血缘、信任与生命周期；git 提供版本快照，使「提取时源数据长什么样」可被 diff 还原，是维测的免费地基。**备选**：源数据进 DB、业务知识进 git —— 否决，因血缘链在源数据端断裂，无法回答「当初基于什么写的」。

### D2: 两条知识管线（文档线 + 代码线）

- **文档线**：数据源 → 连接器（同步+归一化）→ `raw/` → 提取 → `knowledge/`。
- **代码线**：代码仓（只读、不改）→ 提取业务知识（`resource` 指向代码文件）→ `knowledge/`；检索层另挂 codegraph 做代码感知检索，代码本体不进 bundle。

**理由**：代码已在自身 git 中版本化，复制进 bundle 会制造灾难性冗余。代码线通过 `resource` 引用与结构化摘要落 concept，检索时由 codegraph 提供符号级检索。

### D3: 连接器 SPI 拆为两阶段

```python
class Connector(Protocol):
    name: str
    def sync(self) -> list[RawItem]:
        # 源侧: 鉴权/分页/限流/增量拉取 → 原始数据
        ...
    def normalize(self, items: list[RawItem]) -> list[Concept]:
        # 归一化: 原始数据 → OKF markdown concept (带 type/frontmatter)
        ...
```

增量去重由导入流水线（Importer）在 bundle 侧的同步状态中按内容指纹完成，连接器本身保持无状态、可单测。

**理由**：同步段与「源平台怎么取数据」耦合，归一化段与「内容长什么样」耦合，是两个正交难点；拆开才能各自独立演进、组合与单测。

### D4: 提取 = AI 起草 + git PR 人工审核，merge 即 verified

流程：LLM 读 `raw/` 概念 → 生成业务知识草稿（`generated.by: ai:<model>`, `status: draft`）→ 以 git PR 提交 → 人工 review diff → merge 时 CI 写 `verified.by: human:<id>`, `status: stable`。

**理由**：复用 git 的 diff/review/blame/history，零 UI 成本跑通闭环；`verified` 徽章在 merge 环节由 CI 盖章，保证「稳定知识必须经人确认」。**备选**：审核 UI（业务人员）—— 后置，作为皮套在 git 流程之上。

### D5: 检索层 = 统一接口 + 多引擎门面

```
对外统一接口 (能力路由 + 引擎适配)
  ├─ markdown RAG (WeKnora 等，可替换)
  └─ codegraph 代码检索
```

外部消费者只感知一个稳定 API，不感知引擎。**理由**：检索层注定多引擎（RAG + 代码），且引擎需可替换、可被评测对比（同一评测集换引擎重跑）。**备选**：直接暴露 WeKnora —— 否决，失去可替换性与评测基准能力。

### D6: 索引与 git commit 版本绑定

检索引擎中的索引对应 `knowledge/` 的某个 git commit，同步（定时或手动）是「从 commit 到索引」的动作，记录索引版本号。

**理由**：支撑回滚（坏 merge 污染索引 → 退上一版本）、审计（「此答案来自 v42」）、评测可比（「B 分测的是哪个知识版本 + 哪个引擎」）。

### D7: 评测双评分（A 分知识质量 / B 分端到端能力）

- A 分：不经生成，判断 `expected_concept` 是否被检索到、知识本身是否正确（度量知识资产质量）。
- B 分：经统一接口完整跑「问题 → 检索 → 生成 → 答案」，对比 `reference_answer`（度量整条链路能力）。

**理由**：知识没写好 vs 检索器不行是两码事，混分无法定位。A 分不依赖引擎，可最早闭环；B 分打在统一接口上，天然支持引擎对比。评测集 git 化后即为知识的「回归测试」，业务知识 merge 时在 CI 跑评测集，掉分即回归。

### D8: 维测 = 过期检测 + sources 血缘回溯 + 重审/废弃/回滚

源数据 `stale_after` 过期或 `resource` 外部源变更 → 沿 `sources` 链回溯受影响业务知识 → 标记 `status: needs-review` → 重新提取/审核；废弃用 `status: deprecated` + `superseded_by`；索引支持回滚到历史 commit。

## Risks / Trade-offs

- [OKF 仅强制 `type`，其余靠约定] → 平台必须自建 type 分类体系、body 模板与 `x-` 前缀扩展键约定，并在 CI 校验；否则各团队元数据漂移。
- [源数据同仓可能随规模膨胀、diff 噪声大] → 先同仓换取完整血缘；规模成问题后再将 `raw/` 拆出独立 bundle，血缘已由 git 快照兜底，拆不拆不伤追溯。
- [LLM 起草质量不稳定] → 草稿必经人工审核才 `verified`；评测 A 分可作审核前自动闸门。
- [LLM-as-judge 评分有偏] → 优先以 `expected_concept` 命中率等确定性指标为主，生成评分作参考。
- [索引同步与 git 状态不一致] → 索引显式绑定 commit，同步过程幂等，可随时重放。

## Migration Plan

全新系统，无迁移。落地顺序即任务拆解：先 git+OKF 存储与合规校验，再连接器与源数据，再提取，再检索同步，再评测，最后维测。

## Open Questions

- 统一接口最终协议（MCP / REST / SDK）—— 先定义能力清单，协议后置，可后续全部提供。
- 起草与评测所调用的具体 LLM 型号 —— 实现期配置项，不影响架构与 spec。
- codegraph 具体选型 —— 作为检索层适配器，可替换，不影响接口契约。
