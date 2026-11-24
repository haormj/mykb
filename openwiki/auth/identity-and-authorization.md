---
type: concept
title: 身份认证与授权
description: mykb 的本地账号、bcrypt 密码、JWT 加服务端 token 白名单的会话机制，以及平台角色与知识库成员角色构成的两级授权模型。
tags: [auth, jwt, authorization, rbac, tokens, security]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-9061bdf9f107c07b607c859c
    resource: repo://mykb/api/deps.py
  - id: openwiki-source-ddb721bc59bfb88535f443af
    resource: repo://mykb/api/routes/auth.py
  - id: openwiki-source-f09dffa5d4715ac599bbc38b
    resource: repo://mykb/api/routes/members.py
  - id: openwiki-source-cdd6e1b0000cb7d399311da5
    resource: repo://mykb/auth/passwords.py
  - id: openwiki-source-510a6955911480eb26ae43a4
    resource: repo://mykb/auth/service.py
  - id: openwiki-source-10b52c9ea58aa74d83b5c0c3
    resource: repo://mykb/auth/tokens.py
  - id: openwiki-source-f58733c2390c5aa1f016da2e
    resource: repo://mykb/db/bootstrap.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 身份认证与授权

mykb 采用两级授权：**平台级角色**决定是否能进入管理面，**知识库成员角色**决定在某个具体知识库内能做什么。认证是本地账号体系，密码用 bcrypt 哈希，登录签发 JWT 并同步写入服务端 token 白名单，使令牌可被吊销。

## 账号与密码

- `register_account` 校验用户名长度 3-50、密码至少 6 位、用户名与邮箱唯一，然后创建用户并默认授予平台 `user` 角色（`mykb/auth/service.py:29`）。
- 密码使用 bcrypt，代价因子 12；输入超过 72 字节会被截断到 bcrypt 上限（`mykb/auth/passwords.py:9`）。
- `verify_password` 在哈希缺失或格式非法时返回 False 而不是抛异常（`mykb/auth/passwords.py:15`）。
- `authenticate` 按用户名查用户并校验密码，失败统一返回 None，由路由映射为 401（`mykb/auth/service.py:64`）。

## 会话：JWT + 白名单

`TokenService` 采用“JWT 证明持有 + 数据库记录使其可撤销”的模型（`mykb/auth/tokens.py:1`）：

- `create` 先 `revoke_all` 删除该用户所有旧 token（单活跃会话），再签发 HS256 JWT，`sub` 为用户 id、`exp` 为过期时间，默认 7 天，同时写入 `user_tokens` 行（`mykb/auth/tokens.py:31`）。
- `validate` 先做 JWT 签名/过期校验，再要求数据库中存在对应且未吊销、未过期的记录，且 payload 的 `sub` 与记录一致（`mykb/auth/tokens.py:51`）。
- `revoke` 删除单条记录，`revoke_all` 删除用户全部记录（`mykb/auth/tokens.py:67`）。

因此登出不是客户端丢弃 token，而是服务端删除白名单记录；后续同一 token 校验失败。每次新登录会让其它会话失效——这是刻意的“单活跃会话”行为。

`TokenService` 在应用启动时以 `JWT_SECRET` 与 `TOKEN_EXPIRES_DAYS` 构造并挂到 `app.state`（`mykb/api/app.py:70`）。

## 平台级角色

引导脚本定义两个平台角色（`mykb/db/bootstrap.py:12`）：

| 角色 | 权限 | 含义 |
| --- | --- | --- |
| `admin` | `["all"]` | 平台管理员，可访问 `/admin`，在知识库检查中被视作 owner |
| `user` | `["basic"]` | 普通平台用户 |

用户与角色是多对多（`user_roles`）。`permissions_for_user` 汇总用户所有角色的权限字符串并返回 `(roles, permissions)`（`mykb/auth/service.py:76`）。`AuthUser.is_platform_admin` 仅判断平台角色名是否为 `admin`（`mykb/api/deps.py:29`）。

SSO 预留：`find_or_create_sso_user` 按 `(provider, external_id)` 查找或创建用户，生成不冲突的用户名并授予默认角色（`mykb/auth/service.py:94`），配合 `users` 表上的 SSO 唯一约束。

## 知识库级角色

知识库成员角色有四级，由 `KB_ROLE_RANK` 定义大小关系（`mykb/api/deps.py:12`）：

```
viewer(1) < editor(2) < admin(3) < owner(4)
```

`ensure_kb_role` 是核心判定函数（`mykb/api/deps.py:83`）：

- 知识库不存在 → 404；
- 平台管理员直接视为 owner（`is_platform_admin=True`），跳过成员校验；
- 非成员 → 403；
- 成员角色低于要求 → 403；
- 通过则返回 `KbAccess(kb, role, is_platform_admin)`。

`require_kb_role(min_role)` 把它包装成 FastAPI 依赖，`min_role` 在导入时即校验合法性，拼写错误会在启动阶段暴露（`mykb/api/deps.py:107`）。

## 角色能力与成员管理约束

- 各路由按最低角色声明权限，完整矩阵见 [HTTP API 与路由](../api/http-api.md)。
- 成员分配有额外规则：普通 admin 只能分配 editor/viewer，只有 owner 能分配 admin；owner 角色不能通过普通修改/删除操作处理，必须走 `transfer` 转让；不能修改或移除同级及更高角色（`mykb/api/routes/members.py:18`）。
- 平台管理员不受上述同级限制，可管理任意成员，但 owner 的移除仍需转让语义。

## 请求链路

1. 客户端在 `Authorization: Bearer <token>` 头携带令牌。
2. `get_current_user` 读取头、调用 `TokenService.validate`、加载用户并汇总角色/权限，构造 `AuthUser`（`mykb/api/deps.py:53`）。
3. 路由可能叠加 `require_platform_admin` 或 `require_kb_role(...)` 做进一步授权。
4. `GET /auth/me` 返回当前用户的角色与权限，供前端渲染（`mykb/api/routes/auth.py:99`）。

## 安全与失败行为

- 所有认证失败统一 401，授权失败统一 403，避免泄露“资源是否存在”的细节（知识库不存在则 404 是一个例外，但仅在已认证后发生）。
- token 泄露可通过登出/重新登录使旧 token 失效，因为白名单删除后校验不再通过。
- 密码哈希使用随机 salt，同一密码多次哈希结果不同。
- `git_credential_enc` 用 `MYKB_SECRET_KEY` 加密存储，避免明文 git token 落库。

## 代表测试

`tests/test_platform_foundation.py` 覆盖注册/登录/登出、未认证 401、错误凭据 401、重复注册 400、平台管理员门禁（普通用户访问 `/admin/users` 403）、成员角色分配限制与所有权转让。
