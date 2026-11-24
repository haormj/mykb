# Design

## Context

现状见 `proposal.md`。关键事实：

- 「文档」「知识」两个页面当前用 antd `Table` 扁平展示；预览统一走 `Drawer + MarkdownView`（`frontend/src/pages/kb/DocumentsTab.tsx`、`KnowledgeTab.tsx`、`frontend/src/components/MarkdownView.tsx`）。
- 后端列表接口已经返回全量概念，且 `concept_id` 本身就是去掉 `.md` 的仓库相对路径（`mykb/okf/bundle.py:97`）；raw 路径形如 `raw/{connector}/{relative}`（`mykb/importing/service.py:217`），knowledge 路径形如 `knowledge/topics/<slug>`（`mykb/extraction/harness.py:44`），zip 导入保留子目录（`mykb/connectors/upload.py:63`）。
- 前端已有纯函数 + vitest 的先例（`frontend/src/lib/markdown.ts`、`markdown.test.ts`、`pages/kb/context.test.ts`）。

因此树所需的信息全部已在前端可用，不需要后端改动。

## Goals / Non-Goals

**Goals:**

- 两个页面各自以目录树呈现对应层级，保持既有导入、评审、任务、删除与预览能力。
- 树的推导逻辑做成可单测的纯函数，组件只负责状态与渲染。
- 刷新（含 1.5s 轮询）不破坏展开/选中状态。

**Non-Goals:**

- 不新增后端接口、不改数据模型、不改 `services/api.ts` 的类型与调用。
- 不做树与预览的左右分栏（先沿用抽屉；后续可作为独立改动）。
- 不把 `.assets/` 资产、`index.md`/`log.md` 等保留文件纳入树。
- 不做目录级批量操作或跨库跳转。

## Decisions

### 1. 前端从现有列表拼树，不加后端接口

用 `listDocuments` / `listKnowledge` 的返回直接构建树。备选是新增 `/kbs/{id}/tree` 返回嵌套结构，但当前接口已一次性返回全量概念，新增接口只会重复读盘、增加维护面且无懒加载收益。将来知识库规模大到需要按目录懒加载时再引入。

### 2. `lib/tree.ts` 提供纯函数 `buildTree`

输入 `items`、`level`、取标题函数，输出 `TreeNode[]`。内部按 `/` 切段建 trie，目录优先、文件在后，逐层用 `localeCompare(..., { numeric: true })` 排序；目录节点累计文件数。纯函数便于覆盖 zip 嵌套、同名文件/目录、根级散文件、空输入等边界。

### 3. 节点 key 使用命名空间

目录用 `dir:<path>`、文件用 `file:<concept_id>`。因为 `concept_id` 去掉了 `.md`，文件 `raw/upload.md` 与目录 `raw/upload/` 会得到相同基名；命名空间避免 antd `Tree` 的 key 冲突（对应 spec「文件与同名文件夹并存」）。

### 4. 沿用抽屉预览，元数据随选中项传入

`MarkdownView` 的渲染、资源鉴权、公式/mermaid、清洗逻辑都直接复用。选中时前端已持有该概念的列表项，把来源/导入任务（文档）或状态/验证/sources（知识）放进抽屉顶部，无需扩展 `/concepts/content` 返回。删除按钮放在抽屉内，仍复用现有 `api.deleteDocument` 与确认弹窗。

### 5. 展开/选中为独立状态，按 key 保持

`expandedKeys`、`selectedKey` 由组件持有，重建树只替换树数据，不清空状态；选中项在刷新后不存在时清空并关抽屉。轮询期间不会出现"树自动折叠"。

### 6. 过滤在客户端完成

按 `title` 或 `concept_id` 做子串匹配，过滤后为命中项保留祖先并自动展开；清空关键字恢复完整树。当前数据量下一次内存过滤足够，不引入防抖以外的基础设施。

### 7. 目录树开启虚拟滚动

给 antd `Tree` 设置 `height` 启用虚拟列表，避免大库一次性渲染全部节点。

### 8. 隐藏冗余层级根

tab 本身已表明层级（文档=raw、知识=knowledge），树直接显示 level 下的子目录与根级散文件，不额外造 `raw`/`knowledge` 根节点。若 level 下直接存在文件，作为根级叶子显示。

## Risks / Trade-offs

- 轮询频繁重建树导致开销或闪烁 → 纯函数构建 + 保留 state + 虚拟滚动；只有 `hasActive` 时才轮询，逻辑与现状一致。
- 删除入口从表格行移到抽屉，可发现性下降 → 抽屉内用明确的危险按钮并保留确认弹窗。
- 标题重名或过长 → 叶子以标题展示并截断，完整 `concept_id` 放入 tooltip 与抽屉头部。
- 只含 `index.md` 的空目录不出现（`iter_concepts` 跳过保留文件）→ 接受；空层级走空状态。
- 过滤时若选中项被隐藏 → 保留选中与预览内容，不做隐式关闭，避免打断阅读。
- 缺乏组件测试设施 → 以 `lib/tree.test.ts` 覆盖树逻辑，组件改动靠 `npm run build`（tsc）与手动验证。

## Migration Plan

无数据迁移。纯前端改动，直接随前端构建发布；若需回滚，回退相关前端文件即可，后端与数据不受影响。

## Open Questions

- 后续是否把抽屉升级为树/预览左右分栏，属于体验增强，可在本改动完成后独立评估，不影响当前 spec 与任务拆分。
