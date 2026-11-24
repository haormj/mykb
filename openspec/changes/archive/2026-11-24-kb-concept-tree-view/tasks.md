# Tasks

## 1. 目录树构建与过滤工具

- [x] 1.1 在 `frontend/src/lib/tree.ts` 定义树节点类型与纯函数 `buildTree(items, level, getTitle)`：按 `concept_id` 路径切段建 trie，目录 key 用 `dir:<path>`、文件 key 用 `file:<concept_id>`，目录优先且文件在后、按 `localeCompare(..., { numeric: true })` 排序，目录累计文件数；验证方式：为 `buildTree` 编写单测并通过
- [x] 1.2 补充 `frontend/src/lib/tree.test.ts`，覆盖 zip 多层嵌套、文件与同名文件夹并存（键不冲突）、根级散文件、目录/文件排序与数字自然序、目录计数、空输入；验证方式：在 `frontend/` 下运行 `npm run test` 全部通过
- [x] 1.3 在 `lib/tree.ts` 实现过滤辅助逻辑（按 `title` 或 `concept_id` 子串匹配、保留祖先、返回需展开的祖先 key），并补充对应单测；验证方式：`npm run test` 中过滤用例通过

## 2. 「文档」页改造

- [x] 2.1 将 `frontend/src/pages/kb/DocumentsTab.tsx` 的文档表格替换为 antd `Tree`（`blockNode` + `showLine` + `height` 虚拟滚动），用 `listDocuments` 数据构建树，点叶子复用 `getConceptContent` + `MarkdownView` 抽屉预览；验证方式：`npm run build` 通过，页面可展开/选中并展示正文
- [x] 2.2 在抽屉中展示文档元数据（完整路径、来源 `resource`、导入任务 id、状态），并为 `canWrite` 成员提供删除入口，复用现有 `api.deleteDocument` 与确认弹窗；验证方式：有权限时删除生成待审变更、无权限时入口不显示
- [x] 2.3 用独立 state 保存 `expandedKeys`/`selectedKey`，在轮询与手动刷新重建树后保持展开与选中，选中项消失时关闭抽屉；空层级显示空状态；验证方式：导入任务运行时观察轮询刷新后展开/选中不丢失
- [x] 2.4 增加按标题/路径过滤的输入框，命中项保留祖先并自动展开、清空恢复完整树；验证方式：过滤后仅剩匹配项，清空后树恢复
- [x] 2.5 保留导入入口、「待审变更（文档级 MR）」与「导入任务」两张表及其原有操作；验证方式：三项功能与改造前一致可正常使用

## 3. 「知识」页改造

- [x] 3.1 将 `frontend/src/pages/kb/KnowledgeTab.tsx` 表格替换为同款 `Tree`，用 `listKnowledge` 构建树，点叶子复用 `MarkdownView` 抽屉预览；验证方式：`npm run build` 通过，页面可展开/选中并展示正文
- [x] 3.2 在抽屉中展示知识元数据（完整路径、`status`、`verified`、血缘 `sources`），复用同一套树状态（展开/选中保持）与过滤输入；验证方式：切换刷新后状态保持，元数据正确显示
- [x] 3.3 空层级显示空状态，不出现空白树；验证方式：新建空知识库时知识页显示空状态

## 4. 集成验证

- [x] 4.1 在 `frontend/` 下运行 `npm run test` 与 `npm run build`（含 tsc）全部通过；验证方式：命令退出码为 0
- [ ] 4.2 手动回归：导入包含子目录的 zip 后文档页树结构正确、预览与删除可用；知识页树与预览正常；验证方式：逐项操作符合预期

## Workflow follow-up

- 实现完成并通过项目评审后归档该 change。
