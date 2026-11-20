# Design

## Context

`frontend/src/components/AppLayout.tsx` 是全站外壳：`Sider` 内是 `.brand` 与导航菜单，`Header` 内是 `.header-title`、用户信息与退出按钮，`Content` 通过 `<Outlet />` 渲染路由页面。知识库列表页 `pages/KnowledgeBases.tsx` 已在大页面通过 `api.listKbs()` 拉取数据并负责新建，点击列表项跳转 `/kbs/:kbId`；详情页负责 tab 与内容。See `proposal.md - Why`.

约束：

- 不改动既有路由、页面与权限逻辑。
- 知识库列表继续由 `/kbs` 页面承载，侧边栏不重复展示列表。

## Goals / Non-Goals

**Goals:**

- 外壳文案与信息架构对齐：侧边栏品牌「企业知识管理平台」，顶部标题「知识库」。
- 侧边栏只保留一个「知识库」入口，指向大页面的知识库列表。
- 进入 `/kbs` 或任意 `/kbs/:kbId/*` 路由时该入口保持高亮。

**Non-Goals:**

- 不在侧边栏列出知识库，也不在侧边栏提供新建入口。
- 不引入全局状态管理或路由重构。
- 不改动 `/kbs` 列表页与详情页内部布局。

## Decisions

### 1. 侧边栏为静态单入口，不拉取知识库列表

- 方案：`AppLayout` 恢复为静态菜单，仅一个菜单项 `{ key: "/kbs", label: "知识库" }`；不在外壳请求 `api.listKbs()`。
- 理由：知识库列表在大页面展示，侧边栏再拉取会造成重复请求与重复展示；仅 `api.me()` 保持登录态即可。
- 备选：保留侧边栏列表并同时在大页面展示 —— 用户明确希望列表在大页面，因此不采用。

### 2. 选中态

- 由于只有一个入口，直接 `selectedKeys={["/kbs"]}`；`/kbs/:kbId/*` 详情路由也高亮该入口。
- 理由：单入口无需 pathname 归一化；避免为不存在的多入口引入额外逻辑。

### 3. 知识库列表与跳转保持不变

- `pages/KnowledgeBases.tsx` 继续在大页面渲染列表、新建弹窗，并 `navigate(`/kbs/${kb.id}`)` 进入具体知识库。
- 理由：满足“知识库列表在大页面中、点击进入具体知识库”，且改动面最小。

### 4. 清理上一版新增的死代码

- 删除 `frontend/src/components/sidebarNav.ts` 与 `sidebarNav.test.ts`（仅服务于侧边栏列表）。
- 移除 `index.css` 中 `.kb-nav-label` 与 `.ant-menu-inline .ant-menu-title-content { min-width: 0 }`。
- 理由：YAGNI，避免保留不再使用的模块、测试与样式。

### 5. 文案与样式

- `.brand` 文案改为「企业知识管理平台」，沿用现有字号/颜色。
- `.header-title` 文案改为「知识库」，所有页面恒定。

## Risks / Trade-offs

- [用户可能希望从侧边栏直接切换知识库] → 当前需求明确列表在大页面；后续如需可再扩展侧边栏。
- [侧边栏单入口可见性较低] → 顶部标题与大页面列表共同强化「知识库」入口语义。
- [前端导航仅为展示层，权限仍由后端校验] → 列表只来自 `GET /kbs` 的可见集合，深链无权仍由详情页 403 兜底。

## Migration Plan

- 前端资源随现有构建发布，无数据迁移。
- 回滚：还原 `AppLayout.tsx` 与相关样式即可，不影响后端。
- 回归点：登录跳转、`/kbs` 大页面列表、点击进入详情、侧边栏「知识库」高亮、`make build` 与 `cd frontend && npm test`。
