---
type: reference
title: 平台数据模型
description: mykb 在 Postgres 中的元数据表及其关系：账号与角色、知识库与成员、导入任务与提取项、评测集/运行/结果、WeKnora 快照版本与概念映射、发布任务。
tags: [database, sqlalchemy, schema, postgres, metadata]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-9061bdf9f107c07b607c859c
    resource: repo://mykb/api/deps.py
  - id: openwiki-source-ddb721bc59bfb88535f443af
    resource: repo://mykb/api/routes/auth.py
  - id: openwiki-source-f58733c2390c5aa1f016da2e
    resource: repo://mykb/db/bootstrap.py
  - id: openwiki-source-d8b2da3595d5b74f842650ba
    resource: repo://mykb/db/models.py
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 平台数据模型

mykb 采用“元数据入库、内容入 git”的双存储模型：Postgres 只保存平台元数据（账号、权限、知识库注册、任务、评测结果、发布状态），文档与业务知识的正文则存放在每个知识库独立的 OKF git 仓库里。这一分工在 `mykb/db/models.py` 顶部的模块文档中明确声明。本文按业务域梳理这些表及其约束。

## 基础与连接

- 所有模型继承 `mykb/db/base.py` 中的 SQLAlchemy `DeclarativeBase`，`Base.metadata` 同时用于 Alembic 迁移和测试建表。
- 引擎由 `create_db_engine` 构建：生产目标是 Postgres，测试使用 SQLite；SQLite 下显式开启 `PRAGMA foreign_keys=ON`，内存库使用 `StaticPool` 以跨线程共享连接（`mykb/db/session.py:17`）。
- 会话工厂使用 `autoflush=False, expire_on_commit=False`，并提供 `session_scope` 辅助生成器用于提交/回滚（`mykb/db/session.py:38`）。
- JSON 字段使用 `JSONType`，在 Postgres 上映射为 `JSONB`，其他方言退化为 `JSON`（`mykb/db/models.py:30`）。
- ID 多为字符串 UUID（`_uuid()`），时间使用带时区的 `DateTime`，默认 `datetime.now(UTC)`。

迁移按域拆分：`0001_platform_foundation`、`0002_import_tasks`、`0003_extraction_items`、`0004_evaluation_tables`、`0005_weknora_index_tables`、`0006_publish_tasks`。

## 身份与角色

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `users` | `id`、`username`（唯一）、`password_hash`、`email`（唯一）、`display_name`、`sso_provider`/`sso_user_id` | 平台账号，预留 SSO 字段 |
| `roles` | `id`、`name`（唯一）、`permissions`(JSON) | 平台级角色 |
| `user_roles` | `user_id`、`role_id` | 用户与角色多对多，联合唯一 |
| `user_tokens` | `token`（唯一）、`expires_at`、`revoked_at` | 服务端 token 白名单 |

`users` 上还有 `UniqueConstraint("sso_provider", "sso_user_id")`，为将来 SSO 账号绑定留出约束（`mykb/db/models.py:41`）。`user_tokens` 让 JWT 不仅仅是无状态令牌：登出可吊销具体记录，令牌表因此成为服务端白名单（`mykb/db/models.py:66`）。

引导脚本定义了两个平台角色：`admin`（权限 `["all"]`）和 `user`（权限 `["basic"]`），并按 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 幂等创建首个管理员，已存在的账号不会被覆盖（`mykb/db/bootstrap.py:12`）。

## 知识库与成员

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `knowledge_bases` | `name`/`slug`/`local_path`（各自唯一）、`git_url`、`git_branch`、`git_credential_enc`、`owner_id`、`active_weknora_version_id` | 知识库注册与 git 绑定状态 |
| `kb_members` | `(kb_id, user_id)` 复合主键、`role` | 知识库成员角色 |

- `local_path` 唯一，对应 `MYKB_KB_ROOT/<slug>-<id前8位>` 的独立仓库；`git_url` 可空表示仅本地 git 管理（`mykb/db/models.py:88`）。
- `git_credential_enc` 保存加密后的 git 凭据，而不是明文 token。
- `owner_id` 使用 `ondelete="RESTRICT"`，防止误删仍拥有知识库的用户。
- `active_weknora_version_id` 是当前生效检索快照的指针，指向 `weknora_index_versions.id`（`mykb/db/models.py:98`）。
- `kb_members` 的 `role` 取值与 API 层的 `KB_ROLE_RANK`（viewer/editor/admin/owner）一致（`mykb/api/deps.py:12`）。

## 导入与提取

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `import_tasks` | `kb_id`、`source_type`、`status`、计数列 `total/added/updated/skipped/failed`、`error`、`started_at/finished_at` | 一次上传导入的持久任务 |
| `extraction_items` | `kb_id`、`import_task_id`、`concept_id`、`action`、`status`、`branch`、`source_hash`、`title`、`error` | 一份待审文档（文档级 MR） |

- `import_tasks` 有 `(kb_id, created_at)` 索引用于按库列任务，状态字段承载从 `queued` 到终态的流转（`mykb/db/models.py:115`）。
- `extraction_items` 有 `(kb_id, status, created_at)` 索引，支持按库查询待审队列；`action` 区分 add/modify/delete，`branch` 记录该文档对应的 `change/doc-<slug>` 分支（`mykb/db/models.py:151`）。
- `extraction_items.import_task_id` 可空并级联删除，因为文档删除也会生成提取项而没有导入任务；`created_by` 在用户删除时置空（`mykb/db/models.py:158`）。

## 评测

评测是平台级数据，不进入任何 git 仓库：

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `eval_sets` | `owner_user_id`、`name`、`title`、`description` | 平台级可复用评测集 |
| `eval_cases` | `set_id`、`position`、`question`、`reference_answer`、`expected_concept`、`domain`、`difficulty` | 题集中的一道题 |
| `eval_runs` | `set_id`、`target_kb_id`、`triggered_by`、`knowledge_version`、`coverage`、`a_score`、`b_score` | 一个题集对一个目标库的一次运行 |
| `eval_case_results` | `run_id`、`case_id`、快照化的 `question`、`status`、`a_score`、`b_answer`、`b_score` | 逐题结果快照 |

- `eval_sets.cases` 通过关系按 `position` 排序，配置 `cascade="all, delete-orphan"`（`mykb/db/models.py:198`）。
- `eval_case_results` 特意快照 `question`，使日后编辑题集不会改写历史运行的含义，注释中明确说明了这一设计（`mykb/db/models.py:266`）。
- `eval_case_results.case_id` 在题目删除时 `SET NULL`，保留历史结果但解除对活跃题目的引用。
- `eval_runs` 同时有 `(target_kb_id, created_at)` 与 `(set_id, created_at)` 索引，支持按库和按题集的不同查询路径。

## 检索快照与发布

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `weknora_index_versions` | `kb_id`、`git_commit`、`weknora_kb_id`、`status`、`doc_total`/`doc_completed`、`error` | 一个不可变的 WeKnora 快照 |
| `weknora_concept_map` | `version_id`、`concept_id`、`doc_ref` | 概念 id 与快照内文档 id 的映射 |
| `publish_tasks` | `kb_id`、`git_commit`、`status`、`version_id`、进度、`error`、`created_by` | 一次手动发布请求 |

- `weknora_index_versions` 上有两个唯一约束：`(kb_id, git_commit)` 保证同一提交不会重复建快照，`weknora_kb_id` 全局唯一保证每个快照对应独立的 WeKnora 库（`mykb/db/models.py:291`）。
- `weknora_concept_map` 以 `(version_id, concept_id)` 唯一，把平台概念还原为快照内文档（`mykb/db/models.py:323`）。
- `publish_tasks.version_id` 使用 `SET NULL`，发布任务保留历史但可指向已被清理的版本记录；`weknora_index_versions.concept_maps` 配置级联删除（`mykb/db/models.py:347`）。
- 知识库的 `active_weknora_version_id` 与 `weknora_index_versions` 形成“指针 + 不可变版本”的模型，支持发布期间的原子切换与历史回滚。

## 关系与生命周期要点

- 用户删除会级联清除其 `user_roles`、`user_tokens`、`kb_members`、`eval_sets`（`ondelete="CASCADE"`），但知识库 `owner_id` 是 `RESTRICT`，必须先转让或删除知识库。
- 知识库删除会级联清除其成员、导入任务、提取项、评测运行、快照版本与发布任务，因为它们的 `kb_id` 外键均为 `CASCADE`。
- 提取项与导入任务是松耦合的：导入任务可被删除，但提取项通过可空外键保留；文档删除产生的提取项没有导入任务。
- 评测结果的可见性不靠数据库级隔离，而是由 API 层根据目标库成员关系过滤，因此 `eval_runs.target_kb_id` 是权限判定的关键字段。

## 与存储层的边界

`mykb/db/models.py` 只保存“谁、何时、对哪个库做了什么、结果如何”；概念的正文、frontmatter、资产与 git 提交历史全部在 OKF bundle 中。因此评测引用的知识版本用 `knowledge_version`/`git_commit` 这类标识串回指快照，而不是在数据库里存副本。
