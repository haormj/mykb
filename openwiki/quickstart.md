---
type: guide
title: 快速开始
description: mykb 是什么、核心概念、如何安装配置启动，以及按任务（导入、提取评审、检索发布、评测、维护、开发）导航到对应文档。
tags: [quickstart, onboarding, navigation, setup]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-0a1a041fbc31da9e481eb3a4
    resource: repo://frontend/src/pages/Maintenance.tsx
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-303b9ed2b5ad3d75abab2860
    resource: repo://mykb/api/app.py
  - id: openwiki-source-d8b2da3595d5b74f842650ba
    resource: repo://mykb/db/models.py
  - id: openwiki-source-4ccdf13c8842742626ab4110
    resource: repo://mykb/extraction/pipeline.py
  - id: openwiki-source-4c2fbad36351b6670606b9ea
    resource: repo://mykb/okf/model.py
  - id: openwiki-source-a8f7f60ae29342e5de080518
    resource: repo://mykb/retrieval/index.py
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-b452e065fd7a5cd4e87493a8
    resource: repo://tests/test_platform_foundation.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 快速开始

mykb 是企业知识管理平台：用 **Postgres 管理平台元数据**（账号、权限、知识库注册、任务、评测、发布状态），用**每个知识库一个 git 仓库（OKF bundle）承载内容**。源文档经 AI 提取成业务知识，人工评审合入后，手动发布为检索快照。

## 三句话理解它

1. 内容不存数据库：`raw/` 存源文档、`knowledge/` 存业务知识，都在每个库独立的 git 仓库里。
2. 主干恒为已审内容：AI 在 `change/doc-*` 分支上起草，人工按“文档级 MR”评审，合并前不入主干也不进检索。
3. 检索只看快照：只有 `verified && stable` 的业务知识在手动发布后进入检索快照，发布期间旧快照继续服务。

## 安装与启动

```bash
# 1. 安装依赖（后端 uv + 前端 npm）
make setup

# 2. 准备 Postgres（示例）
createdb mykb
export DATABASE_URL=postgresql+psycopg://mykb:mykb@localhost:5432/mykb
export JWT_SECRET=change-me-to-a-long-random-secret
export MYKB_SECRET_KEY=change-me-too

# 3. 建表与创建管理员
make migrate
make bootstrap            # 默认 admin / admin123，可用 ADMIN_USERNAME/ADMIN_PASSWORD 覆盖

# 4. 启动（后端 :8000 + 前端 :5173）
make dev
```

环境要求：Python 3.11+、Node.js 18+、Postgres 14+、`uv`；导入含图片的 `.docx` 需要 `git-lfs`。详细配置项见 [开发、配置与测试](operations/development-and-testing.md)。

登录后进入「知识库」列表，新建知识库即可。系统不预置任何默认知识库。

## 最小可用路线

1. 新建知识库（可选绑定空远程仓库）。
2. 在「文档」页上传 Markdown/docx/zip。
3. 后台自动转换并触发 AI 提取，生成文档级 MR。
4. admin 在「审核」页审批/拒绝/退回，审批即合并并置 `verified && stable`。
5. admin/owner 点「发布」，把合格知识物化为检索快照。
6. 用 `/kbs/{kb_id}/retrieve` 或前端验证命中；在「知识评测」运行评测集。

## 按任务导航

| 我想…… | 读这篇 |
| --- | --- |
| 理解整体架构与端到端流程 | [系统架构总览](architecture/overview.md) |
| 了解数据库表与关系 | [平台数据模型](architecture/data-model.md) |
| 了解 OKF 仓库布局、frontmatter、git/LFS | [OKF 知识存储](architecture/knowledge-storage.md) |
| 弄清账号、JWT 与两级权限 | [身份认证与授权](auth/identity-and-authorization.md) |
| 创建/绑定远程/删除知识库 | [知识库生命周期与 Git 仓库](kb/knowledge-base-lifecycle.md) |
| 上传导入与任务状态 | [文档导入与导入任务](import/document-import.md) |
| 转换 docx 与处理图片资产 | [文档转换与资产处理](import/document-conversion.md) |
| 理解 AI 如何写业务知识 | [AI 知识提取流水线](extraction/knowledge-extraction.md) |
| 评审与合并文档级 MR | [文档级评审与合并](extraction/review-workflow.md) |
| 检索、发布快照与回滚 | [检索与快照发布](retrieval/retrieval-and-publish.md) |
| 配置 WeKnora 检索后端 | [WeKnora 集成](retrieval/weknora-integration.md) |
| 建评测集、跨库对比、看板 | [知识评测与看板](evaluation/knowledge-evaluation.md) |
| 血缘、陈旧、审计、历史回退 | [知识维护](maintenance/knowledge-maintenance.md) |
| 查 HTTP 端点与权限 | [HTTP API 与路由](api/http-api.md) |
| 了解前端页面与权限 UI | [前端应用](frontend/web-application.md) |
| 本地开发、迁移、测试、lint | [开发、配置与测试](operations/development-and-testing.md) |

## 主要接口速览

```
POST /auth/register | /auth/login | /auth/logout      GET /auth/me
GET|POST /kbs                                         知识库注册
GET|PATCH|DELETE /kbs/{kb_id}                         详情/改名/删除
POST /kbs/{kb_id}/remote                              owner 补绑远程
GET|POST|PATCH|DELETE /kbs/{kb_id}/members            成员管理
POST /kbs/{kb_id}/import-tasks                        editor 上传导入
GET  /kbs/{kb_id}/review/mrs                          admin 待审 MR
POST /kbs/{kb_id}/review/mrs/{id}/approve|reject|redraft
POST /kbs/{kb_id}/publish                             admin/owner 发布快照
GET  /kbs/{kb_id}/retrieve | /answer                  viewer 检索/回答
GET  /kbs/{kb_id}/versions                            快照版本
POST|GET /eval/sets                                  平台级评测集
POST /eval/sets/{id}/run                              对目标库运行评测
GET  /eval/overview                                   看板聚合
```

旧的全局路由 `/retrieve`、`/answer`、`/review/drafts`、`/index-sync` 已移除并返回 404；评测统一在平台级 `/eval/*`。

## 需要注意的约束

- 任务执行器是**进程内**的，后端必须以单进程运行（`--workers 1`）；多实例需要外部队列。
- 检索后端未配置 WeKnora 时是进程内内存引擎，重启后快照丢失，需重新发布。
- 导入的原始文件不持久化；失败需重新上传。
- 前端「知识维护」目前是占位页，维护能力尚在库层。

## 测试

```bash
make test            # 后端 pytest（临时 SQLite，不依赖 Postgres）
make lint            # ruff
make typecheck       # mypy
make check           # lint + typecheck + test
make build           # 前端生产构建
cd frontend && npm test   # 前端 vitest
```
