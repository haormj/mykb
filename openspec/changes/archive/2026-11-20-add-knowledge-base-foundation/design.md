# Design

## Context

现状是一个无数据库、无身份、单 bundle 的本地工具：`mykb/api/app.py` 直接读 `MYKB_BUNDLE_ROOT`（默认 `~/.mykb/kb`），所有服务（检索、评测、审核、维护）都围绕这一个根目录。前端没有登录，API 也没有知识库维度。

约束：
- 现有内容层已基于 git + OKF，必须保留（审核=commit、回滚=commit、索引版本=commit）。
- 用户体系参考 `../opencode-qa`：bcrypt 本地账号 + JWT + 服务端 token 白名单 + 预留 SSO 字段；但那边是 Node/Drizzle/SQLite，这里要用 Python + Postgres。
- 本变更范围是平台地基，不含"上传导入"和"把评测/审核/看板迁到前端知识库详情"。

## Goals / Non-Goals

**Goals:**
- 引入 Postgres 数据层与迁移，承载账号、角色、知识库、成员。
- 复刻 opencode-qa 的登录态模型，并预留企业 SSO 身份映射。
- 建立"平台角色 + 知识库成员角色"两级授权，平台 admin 绕过库级校验。
- 每个知识库拥有独立本地 git 仓库（可选远程），知识库之间内容隔离。
- 现有服务与 API 从"全局单库"改为"知识库作用域"。

**Non-Goals:**
- 不做上传导入、导入任务状态机、文档页（后续 `add-document-import-tasks`）。
- 不做前端评测/审核/看板的迁入与设置/成员页（后续 `scope-features-to-knowledge-base`）。
- 不实现真实 SSO 登录流程，仅预留数据字段与抽象。
- 不迁移现有 `~/.mykb/kb` 数据，不创建默认知识库。

## Decisions

### 1. 数据层：Postgres + SQLAlchemy 2.x + Alembic

- 用 SQLAlchemy 声明式模型 + Alembic 管理 schema 版本；驱动 `psycopg`（v3）。
- 开发/测试可用同一套模型，但目标库固定 Postgres（JSONB、部分唯一索引）。
- 备选：继续用 SQLite（opencode-qa 做法）→ 放弃，因为多用户并发与权限查询需要更强的库；Drizzle/Node → 放弃，后端是 Python。

### 2. 身份模型：对齐 opencode-qa，Python 等价实现

```
users
  id UUID pk
  username         text not null unique
  password_hash    text null            -- SSO 用户可为空
  email            text null unique
  display_name     text not null
  sso_provider     text null
  sso_user_id      text null
  created_at, updated_at
  UNIQUE (sso_provider, sso_user_id)

roles
  id serial pk, name text unique, description text, permissions jsonb

user_roles
  id serial pk, user_id fk, role_id fk, assigned_at
  UNIQUE (user_id, role_id)

user_tokens
  id UUID pk, user_id fk, token text unique, user_agent, ip_address,
  expires_at, created_at, revoked_at
```

- 登录签发 HS256 JWT，同时在 `user_tokens` 落库；校验 = 验签 + 查库有效（未吊销、未过期）。
- 与 opencode-qa 一致：登录时吊销该用户旧 token（单活跃会话），代价是一处登录挤掉其它设备；测试期可接受，后续可去掉。
- 密码 `bcrypt`（cost 12）。`JWT_SECRET`、过期天数走环境变量。
- 平台角色种子：`admin`（`permissions=["all"]`）、`user`（`permissions=["basic"]`）。`permissions` 现阶段只透传，实际授权靠角色名，和参考实现保持一致，避免过度设计。

### 3. 两级授权：平台角色 + 知识库成员

```
kb_members
  kb_id UUID fk, user_id UUID fk, role text (owner|admin|editor|viewer),
  created_at
  PRIMARY KEY (kb_id, user_id)
```

- 鉴权依赖链：`get_current_user` → `require_platform_admin` 或 `require_kb_role(kb_id, min_role)`。
- `require_kb_role`：平台 `admin` 直接放行；否则查 `kb_members`，按 `viewer < editor < admin < owner` 比较。
- 能力矩阵固化在权限映射表，路由声明所需最低角色，例如导入=editor、审核=admin、改远程/删除=owner。
- 备选：纯权限字符串（`kb:import` 等）→ 放弃，测试期过重；单层全局角色 → 放弃，无法表达按库授权。

### 4. 知识库 = 元数据(DB) + 本地 git 仓库 + 可选远程

```
knowledge_bases
  id UUID pk
  name         text not null unique
  slug         text not null unique
  git_url      text null
  git_branch   text not null default 'main'
  local_path   text not null unique
  git_credential_enc text null        -- 应用密钥对称加密的 HTTPS token
  owner_id     UUID fk users
  created_at, updated_at
```

- `slug` 由 `name` 派生（小写、非字母数字转 `-`），冲突时追加短后缀；`name` 与 `slug` 均唯一。
- 本地目录 `local_path = <MYKB_KB_ROOT>/<slug>-<id[:8]>`，默认根 `~/.mykb/kbs`；id 后缀保证即使 slug 复用也不重名，DB 唯一约束二次兜底。
- 创建流程（补偿式）：分配 id → 建目录 → `git init` → `ensure_layout()`（复用现有 OKF 布局）→ 首次提交；若配置远程，校验/推送成功才最终提交 DB，任一步失败则删除目录并回滚。
- 未配置远程：仅本地 git，创建成功。后续补绑远程先只允许空远程（`git ls-remote` 无提交），push `-u`。
- git 提交作者统一为服务端身份（沿用 `GitReview` 的 `mykb-agent <agent@mykb.local>`）；"谁触发"记录在业务表/审计，不用个人 git 身份。
- 备选：URL 内嵌 token → 放弃（泄露风险）；每库 SSH key → 测试期不做。

### 5. 作用域路由与运行时上下文

```
/auth/register|login|logout|me
/kbs                         GET(列出可访问), POST(创建)
/kbs/{kb_id}                 GET(详情), PATCH, DELETE
/kbs/{kb_id}/members         ...
/kbs/{kb_id}/retrieve|answer
/kbs/{kb_id}/index-sync
/kbs/{kb_id}/eval/...
/kbs/{kb_id}/review/...
```

- 引入 `KbContext` 解析器：按 `kb_id` 载入 DB 记录 → 构造 `Bundle(local_path)`。
- 检索服务不再在 `app.state` 上缓存单一 `retrieval_service`；改为按 `kb_id` 的缓存字典，`index-sync` / 审核合并后失效对应项。
- `create_app()` 增加数据库会话注入；测试可覆盖 `DATABASE_URL` 与 `MYKB_KB_ROOT`。
- 现有 `Bundle`、`Importer`、`EvalRunner`、`GitReview` 等以 bundle 根为参数，本变更只改变"根从哪来"，尽量不动内部逻辑。

### 6. 迁移与引导

- Alembic 初始迁移创建上述表；启动不自动建表，部署时显式 `alembic upgrade head`。
- 首个平台管理员通过启动引导脚本/环境变量创建（`ADMIN_USERNAME` / `ADMIN_PASSWORD`），避免空系统无人可管。
- 不导入 `~/.mykb/kb`；如需保留由运维自行按新知识库目录手工迁移。

## Risks / Trade-offs

- **BREAKING 路由变更** → 前端与外部消费者全部要改；缓解：同一变更内提供前端登录与知识库外壳，外部接口文档标注版本变化。
- **纯本地知识库只在这台机器** → 服务器损坏即丢失；缓解：产品默认引导配置远程，纯本地标记为"未备份"。
- **同一工作副本并发写** → git 状态错乱；缓解：本变更先加进程内 per-KB 锁，导入任务的串行队列放到后续变更。
- **单活跃会话**（登录吊销旧 token）→ 多设备体验差；缓解：测试期接受，后续改成多 token。
- **凭据加密密钥管理** → 密钥丢失则远程推送失效；缓解：`MYKB_SECRET_KEY` 走部署密钥管理，提供轮换预案。
- **测试依赖 Postgres** → 本地/CI 需容器；缓解：CI 起临时 Postgres，测试用独立 schema 隔离。
- **删除知识库误删本地内容** → 高危；缓解：owner 二次确认，删除先归档目录而非立即物理删除。

## Migration Plan

1. 部署 Postgres 与 Alembic，执行 `alembic upgrade head`。
2. 配置 `DATABASE_URL`、`MYKB_KB_ROOT`、`JWT_SECRET`、`MYKB_SECRET_KEY`；运行管理员引导。
3. 上线后端知识库作用域路由；同版本前端提供登录与知识库列表/详情外壳。
4. 回归：登录、建库（本地/远程）、成员授权、按库检索/评测/审核。
5. 回滚：回退应用版本；DB 保留（新增表不影响旧代码）或用 `alembic downgrade`；本地知识库目录保留待处理。

## Open Questions

- 检索服务是"进程内按 kb 缓存"还是"每次请求重建"——先按 kb 缓存，若内存成为问题再换外部缓存。
- git 凭据加密算法与密钥轮换流程——先用应用级对称加密，细节按部署环境再定。
