---
type: concept
title: 知识库生命周期与 Git 仓库
description: 知识库的注册、本地仓库目录与远程绑定、加密 git 凭据注入、分支与提交作者约定、Git LFS 探测，以及删除、改名与备份等生命周期操作。
tags: [knowledge-base, git, lifecycle, lfs, credentials, registry]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-371c0628f32f17c78ef49a13
    resource: repo://mykb/api/routes/kbs.py
  - id: openwiki-source-69b8cc8c0926f966774458c2
    resource: repo://mykb/crypto.py
  - id: openwiki-source-1e4c2d7d725fb278c143221d
    resource: repo://mykb/kb/context.py
  - id: openwiki-source-91a18e39cc4183c866d2a60b
    resource: repo://mykb/kb/gitops.py
  - id: openwiki-source-3ca438f576fe868606c63723
    resource: repo://mykb/kb/service.py
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 知识库生命周期与 Git 仓库

知识库是 mykb 的隔离单元：每个知识库对应数据库中的一条 `KnowledgeBase` 记录，以及磁盘上一个独立的 git 仓库（OKF bundle）。注册知识库等于同时创建这两者，可选的远程绑定让内容同步到外部 git。本文覆盖创建、绑定远程、修改、访问控制、删除与备份。

## 创建知识库

`create_knowledge_base` 在事务中完成注册与仓库初始化（`mykb/kb/service.py:54`）：

1. 名称去空白后不能为空，且全局唯一，否则 `KnowledgeBaseConflict`（→ HTTP 409）。
2. 生成 `kb_id`（UUID），由名称 slugify 得到 slug，并在冲突时追加序号得到唯一 slug（`_unique_slug`）。
3. 本地路径固定为 `MYKB_KB_ROOT/<slug>-<id前8位>`；若目录已存在则冲突。
4. 若提供 `git_url`，调用 `clone_or_init_with_remote` 克隆远程并初始化布局；否则 `init_local_repo` 创建全新仓库。
5. 若提供 `git_token`，用 `MYKB_SECRET_KEY` 加密后存为 `git_credential_enc`；不存明文。
6. 写入 `KnowledgeBase` 并把创建者加为 `owner` 成员，然后提交。
7. 任一步失败则回滚数据库并删除已创建的本地目录，保证不留半成品。

系统**不预置任何默认知识库**。`slugify` 会做 NFKC 归一化、仅保留字母数字并把空格/连字符/下划线/斜杠折叠为 `-`，空结果回退为 `kb`（`mykb/kb/service.py:28`）。

## 本地仓库布局与初始化

`init_local_repo` 创建目录、`git init -b main`、调用 `Bundle.ensure_layout` 建两级目录与索引，配置 LFS（若可用），再提交 `chore: init bundle`（`mykb/kb/gitops.py:107`）。`clone_or_init_with_remote` 先克隆，再按远程是否存在目标分支决定切换或新建分支，确保布局与 LFS 后提交并推送（`mykb/kb/gitops.py:119`）。

git 提交作者固定为 `mykb-agent <agent@mykb.local>`，通过命令行 `-c user.name/user.email` 注入，不依赖宿主 git 配置（`mykb/kb/gitops.py:12`）。

分支约定：主干 `main`；每份待审文档一个 `change/doc-<slug>-<id前8位>` 分支，审批时用 `--no-ff` 合并（`mykb/extraction/pipeline.py`）。`git_branch` 字段记录远程跟踪分支，默认为 `main`。

## 远程绑定与凭据

- 远程 URL 通过 `inject_credential` 把 HTTPS token 注入为 `oauth2:<token>@host` 形式，仅对 http/https 生效（`mykb/kb/gitops.py:22`）。
- `bind_remote`（服务层）只在**空远程**上允许绑定：`gitops.bind_remote` 先用 `ls-remote` 检查，远程已有提交则报错（`mykb/kb/gitops.py:150`）。
- 绑定 HTTPS 远程时要求宿主安装了 `git-lfs`，并探测远程是否支持 LFS（`git lfs locks --remote`），不支持则拒绝，避免派生资产无法推送（`mykb/kb/gitops.py:94`）。绑定后执行 `push -u origin <branch>`。
- 凭据加密用 Fernet：以 `MYKB_SECRET_KEY` 的 SHA-256 派生 Fernet key，`encrypt_secret`/`decrypt_secret` 负责加解密；解密失败抛 `CredentialError`（`mykb/crypto.py:12`）。`remote_credential` 在需要推送/克隆时按需解密（`mykb/kb/service.py:108`）。
- API `POST /kbs/{kb_id}/remote` 仅 owner 可调用；若请求带新 `git_token` 则更新加密凭据，否则沿用已存凭据（`mykb/kb/service.py:116`）。

## 访问控制与可见范围

- `accessible_bases` 返回当前用户可访问的 `(kb, role)`：平台管理员看到全部（角色记为 owner），普通用户只看自己是成员的库（`mykb/kb/service.py:131`）。
- `GET /kbs` 与评测 overview/runs 等聚合都基于该函数，因此知识库隔离在数据查询层就成立。
- 具体权限判定由 `ensure_kb_role` 完成，详见 [身份认证与授权](../auth/identity-and-authorization.md)。

## 修改与生命周期操作

- `PATCH /kbs/{kb_id}`（admin）可改名与改 `git_branch`；改名同样要求全局唯一，冲突返回 409（`mykb/api/routes/kbs.py:112`）。
- 成员管理（`/kbs/{kb_id}/members`）支持增删改与所有权转让，规则见 [HTTP API 与路由](../api/http-api.md)。
- `DELETE /kbs/{kb_id}`（owner）不直接销毁内容：它把本地仓库目录**重命名移入** `MYKB_KB_ROOT/.trash/<kb_id>`，再删除数据库记录（`mykb/api/routes/kbs.py:137`）。这给误删留了恢复余地（内容仍在磁盘上），但数据库关联（成员、任务、评测、快照）会随知识库级联删除。

## 运行时上下文

`bundle_for(kb)` 用 `kb.local_path` 构造 `Bundle`，让路由与流水线读写内容。`RetrievalCache` 按知识库缓存读服务对象，但每次查询都从数据库解析 active 快照，所以发布切换指针无需跨进程失效缓存（`mykb/kb/context.py:18`）。审批/合并后调用 `cache.invalidate(kb_id)` 让下一次请求重建服务。

## Git LFS 与备份

- 仓库初始化会写入图片类型的 `.gitattributes` 并执行 `git lfs install --local`；没有 `git-lfs` 时跳过配置，保证纯 Markdown 部署可用（`mykb/kb/gitops.py:68`）。
- 导入含图片的文档要求宿主具备 `git-lfs`，否则转换阶段拒绝。
- 备份知识库时必须包含 `.git/lfs/objects`，或依赖远程 LFS 对象，否则恢复后图片只剩指针；本地空间可用 `git lfs prune` 清理未引用对象。

## 失败与一致性

- 创建过程中任何异常都会回滚数据库并删除新建目录，不会留下“有记录无仓库”或“有仓库无记录”的状态。
- 绑定远程失败（远程非空、无 LFS、无 git-lfs）会抛 `GitError` → 400，且不改动 `git_url`。
- 删除采用“移到 .trash + 删记录”，因此需要清理时人工清空 `.trash` 即可，不会立即丢失内容。

## 代表测试

`tests/test_platform_foundation.py` 覆盖创建/重名冲突、绑定空远程与冲突、错误远程回滚、成员角色与转让；`tests/test_gitops.py` 与 `tests/test_git_lfs.py` 覆盖本地初始化、克隆、凭据注入、LFS 探测与提交；`tests/test_document_import.py` 覆盖远程推送与同库串行。
