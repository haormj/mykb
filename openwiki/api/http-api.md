---
type: reference
title: HTTP API 与路由
description: mykb 的 FastAPI 应用装配、路由分组与作用域约定，以及身份、知识库成员、导入、评审、检索发布和评测各端点的权限要求。
tags: [api, fastapi, routing, http, reference]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-303b9ed2b5ad3d75abab2860
    resource: repo://mykb/api/app.py
  - id: openwiki-source-9061bdf9f107c07b607c859c
    resource: repo://mykb/api/deps.py
  - id: openwiki-source-a955c4ef47eaac0fdf1a4555
    resource: repo://mykb/api/routes/documents.py
  - id: openwiki-source-7682159af48c7c129cb11254
    resource: repo://mykb/api/routes/evaluation.py
  - id: openwiki-source-cfcce8b424790f15abe688d1
    resource: repo://mykb/api/routes/import_tasks.py
  - id: openwiki-source-371c0628f32f17c78ef49a13
    resource: repo://mykb/api/routes/kbs.py
  - id: openwiki-source-f09dffa5d4715ac599bbc38b
    resource: repo://mykb/api/routes/members.py
  - id: openwiki-source-cd33e70fba9662f391105f04
    resource: repo://mykb/api/routes/publish.py
  - id: openwiki-source-e505b7019d6a17328bbf6e7c
    resource: repo://mykb/extraction/queue.py
  - id: openwiki-source-10133604e05abac5ade9afe0
    resource: repo://mykb/importing/service.py
  - id: openwiki-source-b452e065fd7a5cd4e87493a8
    resource: repo://tests/test_platform_foundation.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# HTTP API 与路由

mykb 的 HTTP 层是一个 FastAPI 应用，所有路由都通过 `mykb/api/app.py` 的 `create_app` 装配。接口按作用域分层：身份与会话在 `/auth`，平台管理在 `/admin`，知识库注册在 `/kbs`，而内容操作统一挂在 `/kbs/{kb_id}` 之下，评测则是平台级 `/eval`。本文汇总装配方式、分组、权限和关键错误语义，便于从接口反查实现。

## 应用装配与共享状态

`create_app` 在创建应用时解析 `Settings`，构建数据库 engine/session factory、JWT 服务、检索后端、检索缓存、文档转换服务和导入线程池，并把它们挂到 `app.state` 上供依赖注入读取（`mykb/api/app.py:63`）。

- 导入与发布任务都由 `ThreadPoolExecutor(max_workers=4)` 执行，因此路由本身只负责落库和提交任务，真正的转换、提取和快照发布在后台线程完成（`mykb/api/app.py:58`）。
- lifespan 启动时调用 `mark_stale_running_failed` 与 `recover_processing`，把上次进程残留的导入任务标记失败、把 `processing` 的提取项放回队列（`mykb/api/app.py:64`）。
- 提供未鉴权的 `GET /health` 健康检查（`mykb/api/app.py:97`）。
- 路由按 `auth`、`admin`、`kbs`、`members`、`knowledge`、`retrieval`、`publish`、`evaluation`、`review`、`import_tasks`、`documents`、`concepts` 顺序 include（`mykb/api/app.py:103`）。

## 路由分组一览

| 前缀 | 模块 | 作用域 |
| --- | --- | --- |
| `/auth` | `routes/auth.py` | 注册、登录、登出、当前用户 |
| `/admin` | `routes/admin.py` | 平台管理员用户列表 |
| `/kbs` | `routes/kbs.py` | 知识库注册、详情、修改、删除、补绑远程 |
| `/kbs/{kb_id}/members` | `routes/members.py` | 成员与角色管理、所有权转让 |
| `/kbs/{kb_id}/documents` | `routes/documents.py` | 源文档列表与删除（生成删除变更） |
| `/kbs/{kb_id}/concepts` | `routes/concepts.py` | 概念 markdown 正文与资产预览 |
| `/kbs/{kb_id}/knowledge` | `routes/knowledge.py` | 业务知识只读投影 |
| `/kbs/{kb_id}/import-tasks` | `routes/import_tasks.py` | 上传导入任务创建、列表、取消 |
| `/kbs/{kb_id}/review` | `routes/review.py` | 草稿与文档级评审 MR |
| `/kbs/{kb_id}/retrieve`、`/answer` | `routes/retrieval.py` | 知识检索与回答 |
| `/kbs/{kb_id}/publish`、`/versions` | `routes/publish.py` | 手动发布、发布进度、快照版本 |
| `/eval` | `routes/evaluation.py` | 平台级评测集、运行、趋势、看板 |

路由前缀与权限依赖在各模块的 `APIRouter(prefix=...)` 中声明，例如知识库前缀为 `/kbs`（`mykb/api/routes/kbs.py:32`），评测前缀为 `/eval`（`mykb/api/routes/evaluation.py:31`）。

## 认证与会话

- `POST /auth/register` 直接校验并创建账号，返回 `{token, user}`；`POST /auth/login` 校验凭据后同样签发 token；`POST /auth/logout` 吊销当前 Bearer token；`GET /auth/me` 返回当前用户及其平台角色和权限（`mykb/api/routes/auth.py:44`）。
- 所有受保护端点从 `Authorization: Bearer <token>` 头读取 token，经服务端 `TokenService.validate` 校验，缺失或无效返回 401（`mykb/api/deps.py:53`）。
- `GET /admin/users` 仅平台管理员可访问，否则 403（`mykb/api/routes/admin.py:17`）。

## 知识库与成员

- `GET /kbs` 只返回当前用户可访问的知识库及其 `my_role`；平台管理员可见全部；`POST /kbs` 创建知识库，名称冲突返回 409，git 远程失败等业务错误返回 400（`mykb/api/routes/kbs.py:67`）。
- `GET|PATCH|DELETE /kbs/{kb_id}` 分别要求 viewer、admin、owner；删除时把仓库目录移入 `.trash` 再删数据库记录（`mykb/api/routes/kbs.py:137`）。
- `POST /kbs/{kb_id}/remote` 仅 owner 可补绑远程仓库（`mykb/api/routes/kbs.py:157`）。
- 成员接口 `GET|POST|PATCH|DELETE /kbs/{kb_id}/members` 区分 viewer/admin，`POST /members/{user_id}/transfer` 仅 owner。普通 admin 只能分配 editor/viewer，只有 owner 能分配 admin，且不能修改或移除同级及更高角色；owner 不能直接移除，需走转让（`mykb/api/routes/members.py:18`）。

## 文档、概念预览与导入

- `GET /kbs/{kb_id}/documents` 以 viewer 权限列出 `raw/` 下的源文档；`DELETE /kbs/{kb_id}/documents/{concept_id}` 以 editor 权限把删除包装成一条待审变更（`ACTION_DELETE`）并立即触发提取流程，而不是直接删除主干（`mykb/api/routes/documents.py:37`）。
- `GET /kbs/{kb_id}/concepts/content` 返回单个概念的 level、title、body；`GET /kbs/{kb_id}/concepts/asset` 返回 `name` 指定的资产字节，二者均要求 viewer 且拒绝 `index.md`/`log.md` 保留文件名（`mykb/api/routes/concepts.py:14`）。
- `GET /kbs/{kb_id}/knowledge` 返回业务知识只读投影，含 `concept_id`、`status`、`type`、`verified`、`sources`（`mykb/api/routes/knowledge.py:15`）。
- `POST /kbs/{kb_id}/import-tasks` 以 editor 权限接收 multipart `files`，先 `prepare_upload` 暂存，再落库并提交后台任务，返回 201（`mykb/api/routes/import_tasks.py:39`）。列表与详情要求 viewer，取消要求 editor。

## 提取与评审

评审端点全部要求知识库 `admin` 角色（平台管理员视同 owner）（`mykb/api/deps.py:83`）：

- `GET /review/drafts`、`GET /review/diff`、`POST /review/approve` 面向旧的草稿增量审核（`mykb/api/routes/review.py:26`）。
- `GET /review/mrs` 列出 `reviewing/queued/processing` 的文档级 MR；`GET /review/mrs/{item_id}/diff` 用 `gitops.changed_files_vs`/`diff_text` 对比 `main` 与变更分支（`mykb/api/routes/review.py:107`）。
- `POST /review/mrs/{item_id}/approve|reject|redraft` 分别调用提取流水线的 `approve_item`、`reject_item`、`redraft_item`，`PipelineError` 转 400（`mykb/api/routes/review.py:129`）。

## 检索与发布

- `GET /kbs/{kb_id}/retrieve?q=&kind=&top_k=` 通过 `RetrievalCache.get(kb)` 取得该库的检索服务并返回 `asdict(RetrievalResponse)`；`/answer` 返回 `{query, answer}`。二者要求 viewer（`mykb/api/routes/retrieval.py:19`）。
- `POST /kbs/{kb_id}/publish` 要求 admin，若已有进行中的发布任务则返回 409，否则记录当前 HEAD 提交并提交后台发布任务，返回 202（`mykb/api/routes/publish.py:24`）。
- `GET /kbs/{kb_id}/publish/{task_id}` 返回发布进度（status/doc_completed/doc_total/error），要求 viewer 且任务必须属于该库（`mykb/api/routes/publish.py:68`）。
- `GET /kbs/{kb_id}/versions` 列出快照版本并标记 `is_active`（`mykb/api/routes/publish.py:82`）。

## 评测（平台级）

评测集是平台级共享资源，而不是知识库子路由：

- `POST|GET /eval/sets` 创建或列出评测集；`GET|PATCH|DELETE /eval/sets/{set_id}` 中修改与删除仅创建者或平台管理员可做，否则 403（`mykb/api/routes/evaluation.py:146`）。
- `POST /eval/sets/{set_id}/run` 接受 `target_kb_ids`，先以 editor 权限逐个校验目标库（任一失败则不产生任何运行），再对每个目标库运行并保存结果（`mykb/api/routes/evaluation.py:216`）。
- `GET /eval/runs` 可按 `kb_id` 或 `set_id` 过滤；不带 `kb_id` 时聚合当前用户可访问库范围内的运行（`mykb/api/routes/evaluation.py:254`）。
- `GET /eval/runs/{run_id}` 要求对目标库至少有 viewer 权限；`GET /eval/sets/{set_id}/trend` 按目标库返回趋势；`GET /eval/overview` 返回可见库、评测集和运行的看板聚合（`mykb/api/routes/evaluation.py:291`）。

## 权限矩阵（最低角色）

| 操作 | 最低角色 |
| --- | --- |
| 查看知识库、成员、文档、知识、概念、检索、版本、发布进度 | viewer |
| 上传导入、取消任务、删除文档、运行评测（目标库） | editor |
| 修改知识库、管理成员、评审 MR、发起发布 | admin |
| 删除知识库、补绑远程、转让所有权 | owner |

平台管理员在知识库检查中被视作 owner（`mykb/api/deps.py:73`），但平台用户列表等 `/admin` 端点仍只认平台 `admin` 角色。

## 已移除的旧路由

旧的全局内容路由已移除并返回 404：`/retrieve`、`/answer`、`/review/drafts`、`/index-sync`；评测也不再是 `/kbs/{kb_id}/eval/*`，统一迁移到平台级 `/eval/*`（`tests/test_platform_foundation.py:233`）。迁移后访问这些路径不会命中任何路由。

## 错误语义

- `require_kb_role` 在知识库不存在时返回 404，非成员返回 403，角色不足返回 403（`mykb/api/deps.py:99`）。
- 业务校验错误普遍映射为 400（如上传格式、成员分配非法、评审流水线错误），唯一性冲突映射为 409（知识库名称、重复成员、并发布）。
- 评测运行对多个目标库采用“全有或全无”的权限预检，避免部分成功留下不一致的运行记录。

## 代表测试

`tests/test_platform_foundation.py` 覆盖了注册/登录/登出、平台管理员门禁、知识库隔离检索、成员角色分配限制、旧路由 404 以及知识只读投影。`tests/test_e2e.py` 与 `tests/test_platform_foundation.py` 中的评测用例验证了平台级 `/eval` 路由的鉴权与结果可见性。
