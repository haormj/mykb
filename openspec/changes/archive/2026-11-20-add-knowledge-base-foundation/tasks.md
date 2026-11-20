# Tasks

## 1. 数据层与配置

- [x] 1.1 在 `pyproject.toml` 增加 `SQLAlchemy`、`Alembic`、`psycopg`、`PyJWT`、`bcrypt` 依赖，验证 `uv pip install --python .venv/bin/python -e ".[dev]"` 成功且可导入各库
- [x] 1.2 新增 `mykb/db`（engine、session、Base）并读取 `DATABASE_URL`、`MYKB_KB_ROOT`、`JWT_SECRET`、`MYKB_SECRET_KEY`，验证缺失必需配置时启动报清晰错误
- [x] 1.3 定义 `users`、`roles`、`user_roles`、`user_tokens`、`knowledge_bases`、`kb_members` 模型与唯一约束，验证 mypy 通过且针对唯一约束的测试通过
- [x] 1.4 初始化 Alembic 并生成首个迁移，验证 `alembic upgrade head` 后表齐全、`alembic downgrade base` 可回滚
- [x] 1.5 增加管理员引导（`ADMIN_USERNAME` / `ADMIN_PASSWORD`），验证重复执行幂等且不覆盖已存在账号

## 2. 身份与平台授权

- [x] 2.1 实现注册、登录、登出、当前用户接口，含 bcrypt 校验、JWT 签发与 `user_tokens` 落库/吊销，验证 auth 路由测试覆盖成功与失败分支
- [x] 2.2 实现 `get_current_user` 依赖与 `require_platform_admin`，验证无 token 返回 401、普通用户访问管理接口返回 403
- [x] 2.3 增加平台角色种子（admin/user）与新账号默认角色分配，验证新注册账号获得 `user` 角色
- [x] 2.4 落库 `sso_provider` / `sso_user_id` 唯一约束与映射查询，验证相同外部身份重复写入时复用同一账号

## 3. 知识库注册与 git 生命周期

- [x] 3.1 实现 slug 派生、`name`/`slug`/`local_path` 唯一校验与 `local_path` 计算（`<root>/<slug>-<id[:8]>`），验证重复名与路径冲突用例
- [x] 3.2 实现本地知识库创建：建目录、`git init`、`ensure_layout()`、首次提交、DB 落库及失败补偿清理，验证创建后目录含 OKF 布局与首个 commit
- [x] 3.3 实现创建时可选远程：clone/校验、初始化后 push、失败回滚，验证临时空远端与非空/不可达远端用例
- [x] 3.4 实现 owner 补绑远程（仅允许空远程），验证空远程 push 成功、非空远程被拒绝
- [x] 3.5 实现知识库列表与详情接口并按成员/平台管理员过滤，验证列表不包含无权访问的知识库

## 4. 成员与库级授权

- [x] 4.1 实现 `kb_members` 添加/移除/改角色及角色边界（不得授出高于自身），验证越权提升被拒绝
- [x] 4.2 实现 `require_kb_role(kb_id, min_role)`、平台 admin 绕过与能力矩阵映射，验证四档角色在各操作上的允许/拒绝用例
- [x] 4.3 实现 owner 转让，验证转让后双方权限随之变化

## 5. 作用域路由迁移

- [x] 5.1 实现 `KbContext` 解析（kb_id → DB 记录 → `Bundle(local_path)`）与按 kb 的检索服务缓存/失效，验证按库检索只返回该库内容
- [x] 5.2 将 `retrieve`、`answer`、`index-sync`、`eval/*`、`review/*` 路由迁到 `/kbs/{kb_id}/...` 并加库级鉴权，验证旧全局路由返回 404、新路由鉴权正确
- [x] 5.3 在审核合并与索引同步后失效对应 kb 缓存，验证库 A 变更不影响库 B 的检索结果

## 6. 前端登录与知识库外壳

- [x] 6.1 实现登录页、token 持久化与请求自动附带、未登录路由守卫，验证未登录跳转登录页、登录后进入列表
- [x] 6.2 实现知识库列表（新建含名称与可选 git 地址）与详情外壳（文档/知识/设置 tab 占位），验证从创建到进入详情的流程可用
- [x] 6.3 暂时隐藏已迁移的评测/审核/看板入口避免调用失效接口，验证 `npm run build` 通过且导航无死链

## 7. 集成验证与文档

- [x] 7.1 更新 README 与 Makefile 中的环境变量、`alembic upgrade head` 与管理员引导步骤，验证按文档可从零启动
- [x] 7.2 补充端到端集成测试：登录 → 建库 → 加成员 → 按库检索/评测/审核，验证 `pytest`、`mypy mykb`、`ruff check` 全部通过
- [x] 7.3 回归验证：系统无默认知识库、未登录请求被拒、跨库内容不可见，验证 `make check` 与 `npm run build` 通过

## Workflow follow-up

- 评审通过后归档该变更，并确认主 specs 已包含新能力与修改后的能力。
- 归档后再分别创建 `add-document-import-tasks` 与 `scope-features-to-knowledge-base` 两个后续变更。
