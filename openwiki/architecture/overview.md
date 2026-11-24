---
type: architecture
title: 系统架构总览
description: mykb 的分层架构：Postgres 承载平台元数据、每个知识库独立 git/OKF 仓库承载内容、进程内任务执行器、可插拔检索后端与快照发布，以及从导入到评测的主流程。
tags: [architecture, overview, workflow, storage, retrieval]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-303b9ed2b5ad3d75abab2860
    resource: repo://mykb/api/app.py
  - id: openwiki-source-58aae222af55e2808de9efbf
    resource: repo://mykb/config.py
  - id: openwiki-source-d8b2da3595d5b74f842650ba
    resource: repo://mykb/db/models.py
  - id: openwiki-source-4ccdf13c8842742626ab4110
    resource: repo://mykb/extraction/pipeline.py
  - id: openwiki-source-1e4c2d7d725fb278c143221d
    resource: repo://mykb/kb/context.py
  - id: openwiki-source-4c2fbad36351b6670606b9ea
    resource: repo://mykb/okf/model.py
  - id: openwiki-source-a8f7f60ae29342e5de080518
    resource: repo://mykb/retrieval/index.py
  - id: openwiki-source-abbe81a7773046eadbc9c4c3
    resource: repo://mykb/retrieval/publish.py
  - id: openwiki-source-6e885b3cc2fc4659c9941bad
    resource: repo://mykb/retrieval/read.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 系统架构总览

mykb 是企业知识管理平台，核心设计是**元数据与内容分离**：Postgres 管理平台侧状态，每个知识库则对应一个独立的 git 仓库（OKF bundle）承载正文。围绕这一划分，系统由 API 层、进程内任务执行器、OKF 存储层、提取流水线、检索/发布子系统和评测子系统组成。本文给出整体骨架和端到端主流程，细节见各专题页面。

## 分层结构

```
浏览器 (React SPA)
      │  HTTP / JSON
┌─────▼───────────────────────────────┐
│ FastAPI 应用 (mykb/api)             │
│  /auth /admin /kbs/{id} /eval       │
└─────┬───────────────┬───────────────┘
      │               │ 后台任务 (ThreadPoolExecutor)
┌─────▼──────┐  ┌─────▼──────────────┐
│ Postgres   │  │ 导入/提取/发布 worker │
│ 元数据      │  └─────┬──────────────┘
└────────────┘        │
              ┌───────▼────────────────┐
              │ 每库一个 git OKF bundle │
              │  raw/ + knowledge/      │
              └───────┬────────────────┘
                      │ 发布物化快照
              ┌───────▼────────────────┐
              │ 检索后端 (本地内存/WeKnora) │
              └────────────────────────┘
```

- **API 层**：`create_app` 组装依赖并挂载路由；共享状态（DB、token 服务、检索后端、检索缓存、转换服务、导入线程池）存在 `app.state`（`mykb/api/app.py:63`）。接口按作用域组织，见 [HTTP API 与路由](../api/http-api.md)。
- **元数据层**：所有账号、成员、任务、评测、发布状态都进 Postgres，模型见 [平台数据模型](data-model.md)。
- **内容层**：每个知识库在 `MYKB_KB_ROOT/<slug>-<id前8位>/` 下有独立仓库，`raw/` 存源文档、`knowledge/` 存业务知识，见 [OKF 知识存储](knowledge-storage.md)。
- **检索与发布**：检索只读当前 active 快照；发布把 `verified && stable` 业务知识全量物化为新快照，见 [检索与快照发布](../retrieval/retrieval-and-publish.md)。

## 运行期组成

应用启动时（lifespan）会做两件事：把上次残留的 `running` 导入任务标记为 `failed`，并把残留 `processing` 的提取项放回队列（`mykb/api/app.py:64`）。这是因为任务执行器是**进程内**的，单一进程重启会丢掉未完成的工作，而数据库状态需要被修正。

导入、提取和发布共享同一个 `ThreadPoolExecutor(max_workers=4)`，并通过按知识库的锁保证同一库的导入与发布串行、不同库可并行（`mykb/api/app.py:58`、`mykb/api/app.py:80`）。这一设计意味着后端必须以单进程运行（`--workers 1`），多 worker/多实例需要替换为外部队列。

配置全部来自环境变量，`load_settings` 在缺少 `DATABASE_URL`、`JWT_SECRET`、`MYKB_SECRET_KEY` 时直接报错（`mykb/config.py:78`）。可选配置覆盖上传上限、转换 sidecar、知识库资产配额、提取开关、WeKnora 与 LLM 端点。

## 端到端主流程

1. **创建知识库**：登记元数据，初始化 git 仓库与 OKF 布局，可选克隆远程并探测 LFS。详见 [知识库生命周期](../kb/knowledge-base-lifecycle.md)。
2. **导入文档**：上传 Markdown/docx/zip，暂存到 `.tmp/<task_id>`，转换后把源概念暂存到 `.pending/<item_id>` 并生成 `ExtractionItem`。原始上传不持久化，详见 [文档导入](../import/document-import.md) 与 [文档转换](../import/document-conversion.md)。
3. **AI 提取**：提取 worker 按库单飞取队首文档，在 `change/doc-<slug>` 分支上写入 raw 概念，并生成受其影响的业务知识变更，构成文档级 MR。详见 [AI 知识提取流水线](../extraction/knowledge-extraction.md)。
4. **人工评审**：admin 逐份评审 MR，审批后合并到 `main`、为通过的业务知识打 `verified` 并置 `stable`，未合并内容不入主干。详见 [文档级评审与合并](../extraction/review-workflow.md)。
5. **发布快照**：admin/owner 手动触发发布，把当前提交的 `verified && stable` 知识物化为新检索快照，全部就绪后原子切换 active 指针，详见 [检索与快照发布](../retrieval/retrieval-and-publish.md)。
6. **检索与回答**：`/kbs/{kb_id}/retrieve` 在 active 快照上搜索，把后端文档 id 映射回平台概念 id；`/answer` 返回首条命中片段或经 answerer 生成的回答（`mykb/retrieval/read.py:50`）。
7. **评测**：平台级评测集可在多个目标库上运行，产出知识质量分（A）和端到端分（B），详见 [知识评测与看板](../evaluation/knowledge-evaluation.md)。

## 关键不变量

- **内容只在 git 中**：文档与业务知识正文不进数据库，数据库只存标识与状态。
- **主干恒为已审内容**：所有变更先进分支，合并前不影响 `main`，也不进入检索。
- **只有 verified && stable 可检索**：检索可见性由 `Concept.is_verified_stable()` 以及发布时的 `select_indexable_knowledge` 共同约束（`mykb/okf/model.py:145`、`mykb/retrieval/index.py`）。
- **active 快照原子切换**：发布期间检索继续服务上一个快照，新快照全部就绪后才移动指针（`mykb/retrieval/publish.py`）。
- **知识库隔离**：检索、内容、评测结果都按知识库成员关系鉴权。

## 代码地图

| 目录 | 职责 |
| --- | --- |
| `mykb/api` | FastAPI 装配、依赖、路由 |
| `mykb/db` | SQLAlchemy 模型、会话、引导 |
| `mykb/auth` | 账号、密码、JWT/token |
| `mykb/kb` | 知识库注册、git 操作、运行时上下文/检索缓存 |
| `mykb/okf` | bundle 布局、概念模型、校验 |
| `mykb/connectors` | 数据源连接器框架 |
| `mykb/conversion` | 文档转换 sidecar 与资产 |
| `mykb/importing` | 上传导入与导入任务 worker |
| `mykb/extraction` | 提取流水线、harness、队列、评审、LLM |
| `mykb/retrieval` | 检索接口、后端、发布、读路径 |
| `mykb/evaluation` | 评测 runner 与存储 |
| `mykb/maintenance` | 血缘、陈旧、审计、回滚、生命周期 |
| `frontend` | React + Ant Design SPA |

## 运行约束与扩展点

- 任务执行器进程内单进程是当前最重要的部署约束；横向扩展需要外部队列。
- 检索后端可插拔：未配置 `MYKB_WEKNORA_URL` 时用进程内本地后端（开发/测试默认），配置后走 WeKnora。
- LLM 可替换：默认确定性 `FakeLLM` 便于离线测试，配置 OpenAI 兼容端点即接真实模型。
- 文档格式扩展点：转换器按后缀注册，sidecar 返回归一化协议，平台侧改写资产链接。
