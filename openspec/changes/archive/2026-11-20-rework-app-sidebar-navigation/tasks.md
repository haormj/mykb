# Tasks

## 1. 应用外壳文案与侧边栏单入口

- [x] 1.1 将 `.brand` 文案改为「企业知识管理平台」、`.header-title` 文案改为「知识库」，运行 `make build` 验证 tsc + vite 构建通过
- [x] 1.2 将侧边栏恢复为静态单入口「知识库」（`/kbs`），移除 `api.listKbs()` 拉取与逐个知识库菜单，验证 `/kbs` 与 `/kbs/<id>/*` 下该入口高亮
- [x] 1.3 删除不再使用的 `frontend/src/components/sidebarNav.ts`、`sidebarNav.test.ts` 及 `index.css` 中 `.kb-nav-label` 相关样式，运行 `npm test` 与 `make build` 验证无死代码且通过

## 2. 大页面知识库列表与文档

- [x] 2.1 确认 `/kbs` 大页面展示知识库列表且点击列表项进入 `/kbs/<id>`，验证列表与新建交互未改动
- [x] 2.2 更新 `README.md`「界面结构」：左侧仅「知识库」入口、知识库列表在大页面展示，验证文档与界面一致

## 3. 集成回归

- [x] 3.1 回归登录跳转、`/kbs` 大页面列表、点击进入具体知识库、侧边栏「知识库」高亮，运行 `make build` 与 `cd frontend && npm test` 全部通过

## Workflow follow-up

- 评审通过后归档该变更。
- 确认归档后主 specs 无需变动（本变更 `skip_specs: true`）。
