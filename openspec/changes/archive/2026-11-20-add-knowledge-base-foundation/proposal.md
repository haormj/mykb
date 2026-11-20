# Proposal

## Why

当前系统是**单知识库、无身份、无数据库**的本地工具：一个全局 bundle（`~/.mykb/kb`）承载全部内容，API 与前端都没有"知识库"维度，也没有用户与权限。要支撑"新建知识库、按库隔离内容、按用户授权、后续对接公司账号"的企业场景，必须先补齐平台地基：数据库、身份认证、知识库注册与成员权限，并去掉单 bundle 假设。

## What Changes

- 引入 **Postgres** 与数据层（SQLAlchemy + Alembic），新增 `users` / `roles` / `user_roles` / `user_tokens` / `knowledge_bases` / `kb_members` 等表。
- 新增**本地账号体系**：注册、登录、登出、当前用户；JWT + 服务端 token 白名单（可吊销、可过期）。预留 `sso_provider` / `sso_user_id` 字段，后续对接公司账号。
- 新增**两级授权**：平台角色（`admin` / `user`）+ 知识库成员角色（`owner` / `admin` / `editor` / `viewer`）；平台 admin 绕过库级校验。
- 新增**知识库注册**：`name` / `slug` / `local_path` 唯一；创建时在 `~/.mykb/kbs` 下初始化独立 git 仓库与 OKF 布局；`git_url` 可选，未配置则纯本地 git 管理，后续可补绑远程。
- **BREAKING**：现有 API 由全局路径改为知识库作用域（`/kbs/{kb_id}/...`）；检索、评测、审核、维护都绑定到具体知识库；移除服务端的单 bundle 全局根假设。
- 服务端以知识库为运行单位；CLI 与环境变量保留显式 bundle root 能力用于测试与运维。
- 前端新增登录页与知识库列表/详情外壳（文档 / 知识 / 设置 tab 占位）；既有评测、审核、看板页面在后续变更迁入。

## Capabilities

### New Capabilities

- `platform-identity`: 本地账号与登录态（注册、登录、登出、当前用户、JWT + 服务端 token 白名单），并预留 SSO 身份字段。
- `platform-authorization`: 平台级角色与权限（admin / user），平台管理员校验。
- `knowledge-base-registry`: 知识库的创建、查询与本地 git 仓库生命周期（唯一命名、OKF 初始化、可选远程）。
- `knowledge-base-access-control`: 知识库成员与四档角色（owner / admin / editor / viewer）及能力矩阵、库级授权校验。

### Modified Capabilities

- `knowledge-storage`: 由"单一 bundle"改为"每个知识库一个独立 git 仓库与工作副本"，库间内容隔离，本地路径唯一。
- `knowledge-retrieval`: 统一检索与索引同步按知识库维度隔离，而非全局单库。
- `knowledge-evaluation`: 评测集与评测运行归属具体知识库，不再有全局评测集。

## Impact

- **Backend**: `mykb/api/app.py` 路由改为知识库作用域；新增 `mykb/db`（模型 + 会话 + 迁移）、`mykb/auth`（账号、token、鉴权依赖）；检索/评测/审核/维护服务改为接收知识库上下文。
- **Frontend**: 新增登录页、带鉴权的 API 客户端、知识库列表与详情外壳、路由守卫。
- **Dependencies**: 新增 `SQLAlchemy`、`Alembic`、`psycopg`、`PyJWT`、`bcrypt`。
- **Data**: 新增 Postgres schema；现有 `~/.mykb/kb` 不迁移、不建默认知识库，仅由用户新建触发。
- **Ops**: 需要 Postgres 连接配置，以及用于加密 git 凭据的服务端密钥。
- **Follow-up changes**: ② `add-document-import-tasks`（上传导入 + 任务状态机 + 文档页）；③ `scope-features-to-knowledge-base`（评测/审核/看板迁入 + 设置/成员页）。
