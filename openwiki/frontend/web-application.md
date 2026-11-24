---
type: concept
title: 前端应用
description: mykb 的 Vite + React + Ant Design 单页应用：路由与页面布局、知识库详情四个标签页、权限感知 UI、API 服务层与 Markdown/资产预览，以及前端测试。
tags: [frontend, react, vite, antd, routing, ui]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-1047363cf615000e4c9bb694
    resource: repo://frontend/package.json
  - id: openwiki-source-454c9bcdde0b77b35e0fc994
    resource: repo://frontend/src/App.tsx
  - id: openwiki-source-0e1ab8f2525a5d809793c586
    resource: repo://frontend/src/components/AppLayout.tsx
  - id: openwiki-source-3e8745bdab2cc44e818c4bf9
    resource: repo://frontend/src/components/MarkdownView.tsx
  - id: openwiki-source-a8c5f82277fc07c146e59c36
    resource: repo://frontend/src/components/RequireAuth.tsx
  - id: openwiki-source-2040b290534d0bba254efc1a
    resource: repo://frontend/src/lib/markdown.test.ts
  - id: openwiki-source-b6f62c0ce20b053785603ef8
    resource: repo://frontend/src/lib/markdown.ts
  - id: openwiki-source-04a19647831ceacc02947c87
    resource: repo://frontend/src/lib/tree.test.ts
  - id: openwiki-source-51560b579d5ec18b4b643343
    resource: repo://frontend/src/lib/tree.ts
  - id: openwiki-source-0ea459c666c2b8d5a6a45060
    resource: repo://frontend/src/pages/kb/context.test.ts
  - id: openwiki-source-58260c91dec36f8158eeaafe
    resource: repo://frontend/src/pages/kb/context.ts
  - id: openwiki-source-b46a313773ce65a19131927e
    resource: repo://frontend/src/pages/KnowledgeBaseDetail.tsx
  - id: openwiki-source-83ecc4bd5f4eb07c969b9c4b
    resource: repo://frontend/src/services/api.ts
  - id: openwiki-source-378e3cf05ab0d05d335c68d5
    resource: repo://frontend/vite.config.ts
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 前端应用

前端是一个 Vite + React 18 + Ant Design 5 的单页应用，通过 `fetch` 直接调用后端 HTTP API（开发期由 Vite 代理转发）。它不包含业务权限的最终判定权——后端仍是权威——但会根据当前用户角色隐藏无权操作、禁用按钮并给出提示。

## 技术栈与构建

- 依赖见 `frontend/package.json`：`react`/`react-dom` 18、`react-router-dom` 6、`antd` 5、`recharts` 3（图表）、`streamdown` 及 `@streamdown/{cjk,code,math,mermaid}`（Markdown 渲染）、`tailwindcss` 4。
- 构建脚本：`npm run build` 先 `tsc --noEmit` 再 `vite build`；`npm test` 运行 `vitest run`。
- `vite.config.ts` 配置 `@` 别名指向 `src`，并把 `/health`、`/auth`、`/admin`、`/kbs` 以及 `^/eval(?:/|$)` 代理到 `http://localhost:8000`。注意只代理 `/eval` API 而不代理 `/evals` 这条 SPA 路由。
- 入口 `main.tsx` 用 Ant Design `ConfigProvider` 设置中文 locale 与主题色，包裹 `App`。

## 路由结构

`App.tsx` 用 `BrowserRouter` 定义路由（`frontend/src/App.tsx:20`）：

| 路径 | 页面 |
| --- | --- |
| `/login` | 登录/注册（无外壳） |
| `/kbs` | 知识库列表 |
| `/kbs/:kbId` | 知识库详情外壳，默认重定向到 `documents` |
| `/kbs/:kbId/documents` | 文档导入与导入任务 |
| `/kbs/:kbId/knowledge` | 业务知识只读浏览 |
| `/kbs/:kbId/review` | 文档级/草稿审核（admin+） |
| `/kbs/:kbId/settings` | 基础设置、远程仓库、成员管理（admin+） |
| `/evals` | 评测集管理 |
| `/scores` | 知识评测看板 |
| `/maintenance` | 知识维护占位页 |

除 `/login` 外都包在 `RequireAuth` 与 `AppLayout` 中。`RequireAuth` 仅检查 localStorage 中是否存在 token，没有则重定向到 `/login` 并记录来源路径（`frontend/src/components/RequireAuth.tsx:6`）。`/kbs/:kbId/evals` 与 `/scores` 被重定向回文档页，因为评测已迁移到平台级页面。

## 应用外壳与一级导航

`AppLayout` 提供顶部一级菜单「知识库 / 知识评测 / 知识维护」和左侧子菜单（`frontend/src/components/AppLayout.tsx:19`）：

- 知识库：侧栏只有「知识库列表」。
- 知识评测：侧栏「看板」(`/scores`) 与「评测集」(`/evals`)。
- 知识维护：侧栏显示禁用的「暂无页面」占位。

当前一级栏目由路径推断（`sectionOf`）。外壳挂载时调用 `api.me()` 加载当前用户；失败则清除 token 并跳登录。

## 权限感知 UI

知识库详情页根据 `kb.my_role` 计算能力（`frontend/src/pages/kb/context.ts:3`）：

- `WRITE_ROLES = {owner, admin, editor}` → `canWrite`
- `ADMIN_ROLES = {owner, admin}` → `canAdmin`
- `isOwner` 仅在 `role === "owner"`

派生规则函数：

- `roleRank`：viewer<editor<admin<owner，与后端一致。
- `assignableRoles(actorRole)`：owner 可分配 admin/editor/viewer，其他（admin）只能分配 editor/viewer。
- `canManageMember(actorRole, targetRole, canAdmin)`：需要 admin 能力、目标不是 owner、且目标角色严格低于操作者。

详情页据此过滤标签：文档与知识对所有角色可见，审核与设置仅 `canAdmin`；若当前路径段不允许则回落到 `documents`（`frontend/src/pages/KnowledgeBaseDetail.tsx:128`）。深链访问无权知识库时后端返回 403，前端以 `text.startsWith("403")` 识别并展示 403 提示。这些纯函数被 `context.test.ts` 单测覆盖。

## 页面职责

### 知识库列表（`/kbs`）

加载 `GET /kbs`，展示每库名称、角色、本地路径、是否有远程；右上角「新建」弹窗收集名称与可选 `git_url`/`git_branch`/`git_token`，成功后跳转到该库详情。系统不预置任何默认知识库。

### 知识库详情外壳

`KnowledgeBaseDetail` 负责加载库详情、成员和快照版本，并提供发布入口与轮询（`frontend/src/pages/KnowledgeBaseDetail.tsx:24`）：

- 「发布」要求 admin，调用 `POST /publish` 后每秒轮询进度直到离开 `{queued,building,indexing,activating}`；`ready` 提示成功、`failed` 提示错误；遇到 409 提示「已有发布正在进行」。
- 顶部展示当前 active 版本与「未发布：检索暂无结果」提示。
- 通过 router outlet context 把 `kb`、`members`、`refresh` 与权限布尔值传给四个标签页。

### 文档页（`DocumentsTab`）

- 用 `Upload` 选择 Markdown/docx/zip 并提交 `POST /kbs/{id}/import-tasks`（multipart `files`）。
- 列出导入任务并轮询进行中的任务，可取消；对终态任务展示计数。
- 用 `buildTree`/`filterTree` 把 raw 概念概念 id 组织成目录树，点击叶子通过 `getConceptContent` 预览 Markdown。
- 支持删除源文档（生成删除变更），并区分权限。

### 业务知识页（`KnowledgeTab`）

只读展示 `GET /kbs/{id}/knowledge`，按 concept id 的目录结构建树，展示每个概念的 `status`/`type`/来源，并用 `MarkdownView` 渲染正文与派生资产。

### 审核页（`Review`）

面向 admin，既展示平台级文档级 MR（`/review/mrs`）的 diff 与审批/拒绝/退回操作，也可能保留草稿级审核入口；动作对应 `/review/mrs/{id}/approve|reject|redraft`。详见 [文档级评审与合并](../extraction/review-workflow.md)。

### 设置页（`SettingsTab`）

admin 可改基础信息与成员；owner 额外可补绑远程仓库、删除知识库、转让所有权。成员表按 `canManageMember` 与 `assignableRoles` 限制可执行操作，owner 行以标签展示并需通过「转让 owner」处理。

### 评测页（`/evals`、`/scores`）

- `EvalSets`：管理平台级评测集（增删改查），选择目标库运行 `POST /eval/sets/{id}/run`。
- `Scoreboard`：调用 `GET /eval/overview` 与 `GET /eval/runs`，用 recharts 做同题集跨库对比与趋势展示。

### 维护页（`/maintenance`）

当前只是一个占位页，后端已具备血缘/陈旧/审计/回滚能力但尚未接入 UI，见 [知识维护](../maintenance/knowledge-maintenance.md)。

## API 服务层

`frontend/src/services/api.ts` 是唯一的数据访问层（`api.ts` 只是转导出）。要点：

- token 存于 `localStorage` 的 `mykb.token`；`request` 自动加 `Authorization: Bearer`，遇到 401 清除 token。
- 非 `FormData` 的请求自动设置 `Content-Type: application/json`。
- 资产请求单独走 `fetchConceptAsset` 并用 `Bearer` 头拉取 Blob。
- `getJson` 在非 2xx 时抛出形如 `"<status> <text>"` 的错误，页面据此用 `startsWith("403")`/`"409"` 做分支。
- `api` 对象按域分组：identity、knowledge bases、documents & import tasks、settings、平台级 evaluation、scoped review、document-level review MRs。

## Markdown 与资产预览

`MarkdownView` 用 `Streamdown` 渲染，注册 code/mermaid/math/cjk 插件；它先 `stripFrontmatter` 去掉 frontmatter，再用 `rewriteAssetLinks`/`parseAssetUrl` 把概念内的 `.assets/` 相对链接改写为占位 URL，并按需拉取资产 Blob、用 object URL 缓存并在组件卸载时 `revoke`（`frontend/src/components/MarkdownView.tsx:1`）。这些纯函数逻辑在 `lib/markdown.test.ts` 覆盖。

`lib/tree.ts` 把概念 id 的路径段建成 trie 树，目录在前、文件在后并按自然序排序，同名文件与文件夹区分为不同节点；`lib/tree.test.ts` 覆盖这些行为。

## 前端测试

`npm test`（vitest）覆盖纯逻辑：

- `pages/kb/context.test.ts`：角色能力、成员管理边界、可分配角色、角色排序。
- `lib/tree.test.ts`：目录树构建、层级过滤、排序、同名节点区分、顶层文件。
- `lib/markdown.test.ts`：frontmatter 剥离、资产链接解析、资产链接改写。

组件与页面本身没有端到端测试；前端正确性依赖类型检查（`tsc --noEmit`）、这些纯函数单测以及后端集成测试。
