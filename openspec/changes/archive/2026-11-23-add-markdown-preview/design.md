# Design

## Context

知识库每个 KB 是一个 git bundle，概念是带 YAML frontmatter 的 markdown；`Concept.body` 已经是不含 frontmatter 的正文，图片以相对链接 `](<alias>.assets/<name>)` 指向概念同名 `.assets/` 目录。现有后端只有列表接口（`documents`、`knowledge`），前端没有 markdown 渲染能力。鉴权统一走 `require_kb_role("viewer")`，前端以 `Authorization: Bearer` 调 API。参见 `proposal.md` 与 `specs/concept-preview/spec.md`。

## Goals / Non-Goals

**Goals:**
- 用最少的新接口读出概念正文与图片，复用现有 RBAC。
- 前端用统一的 `MarkdownView` 渲染 raw 与 knowledge，支持 GFM、公式、mermaid、图片。
- 图片在携带登录凭据的前提下显示，资产读取严格限制在概念自己的 `.assets/`。

**Non-Goals:**
- 不预览原始上传文档（原始文件不持久化），只预览转换后的 markdown 与派生图片。
- 不改 bundle 布局、不加数据库字段、不把渲染结果落盘。
- 不改造审核页的 diff（本次仅复用渲染能力，不改 diff 交互）。
- 不新增写操作或编辑能力，预览只读。

## Decisions

### 统一的概念内容与资产路由

新增 `mykb/api/routes/concepts.py`，挂在 `/kbs/{kb_id}` 下：

- `GET /kbs/{kb_id}/concepts/content?concept_id=<raw/...|knowledge/...>` → `{concept_id, level, title, body}`
- `GET /kbs/{kb_id}/concepts/asset?concept_id=<...>&name=<file>` → 图片字节 + `Content-Type`

理由：`concept_id` 本身带层级前缀（`raw/` 或 `knowledge/`），一个处理器即可覆盖两个层级，避免在 `documents`/`knowledge` 两个前缀下重复并规避 `:path` 贪婪捕获与后缀 `/content` 的路由歧义。权限仍用 `require_kb_role("viewer")`。proposal 中"raw 与 knowledge 各一个入口"由同一接口的两个 `concept_id` 前缀满足。

替代方案：在 `documents.py`/`knowledge.py` 各加 `/{concept_id:path}/content` —— 路径含 `.docx`、斜杠，且与既有 `DELETE /{concept_id:path}` 组合易产生捕获歧义，放弃；用查询参数传递 `concept_id` 更稳。

### 资产安全放在 Bundle 层

在 `mykb/okf/bundle.py` 增加读取资产的方法（如 `read_asset(concept_id, name) -> (bytes, mime)`）：
- 由 `concept_id` 拆出 `level` 与相对路径（去掉首段层级），复用已有 `asset_dir_for`。
- 校验 `name` 是单段文件名（非空、非 `.`/`..`、不含 `/`、`\`）。
- `resolve()` 后校验父目录就是该概念的 `.assets/`，否则拒绝。

理由：路径拼接与穿越校验集中到 bundle 层，避免各路由重复且更易测试；`name` 单段约束让穿越几乎不可能。

### 后端只返回正文 body

`concept.body` 已剥离 frontmatter，接口直接返回它；前端无需再解析 YAML。`MarkdownView` 仍做一次防御性 frontmatter 剥离（复用 opencode-qa 的正则），保证即使调用方传入带 frontmatter 的文本也不显示元数据。

### 前端采用 Streamdown，版本对齐 opencode-qa

`MarkdownView` 基于 `streamdown`，插件启用 `code`、`mermaid`、`math`、`cjk`，与 `../opencode-qa` 完全一致（`streamdown@^2.5.0`、`@streamdown/code@^1.1.1`、`@streamdown/mermaid@^1.0.2`、`@streamdown/math@^1.0.2`、`@streamdown/cjk@^1.0.3`、`katex@^0.16.44`）。Streamdown 默认用 `rehype-harden` 清洗，满足渲染安全要求；mermaid 为点击后懒渲染，体积成本可控。

替代方案：`react-markdown` 手搭 —— 要自行选 GFM/高亮/公式/清洗，工作量与不一致风险更高，放弃。

### 图片用带凭据的 blob 加载

`<img src>` 不会携带 `Authorization`，因此自定义 `components.img`：识别相对资产链接，取 `.assets/` 后的文件名，调用 `api.fetchConceptAsset(kbId, conceptId, name)`（内部 `fetch` 带 Bearer）→ `blob` → `URL.createObjectURL`，卸载时 `revokeObjectURL`。非资产链接（http/https）交给 Streamdown 默认处理。

### 两个标签页复用同一抽屉

`DocumentsTab` 与 `KnowledgeTab` 各加"预览"入口，打开 antd `Drawer`，内部渲染同一个 `MarkdownView`（传 `kbId`、`conceptId`）。列表接口已含标题/状态，抽屉标题直接复用，不额外取元数据。

### 样式集成照搬 opencode-qa

`frontend/src/index.css` 增加：`@source` 指向 streamdown 及四个插件的 `dist/*.js`、`@import "streamdown/styles.css"` 与 `katex/dist/katex.min.css`、`:root` 的 shadcn 变量（`--background`/`--foreground`/`--border`/`--radius` 等），以及 opencode-qa 里那组动态 utility class 补丁。mykb 与 opencode-qa 同为 Tailwind v4 + 相同 `@theme` token，移植成本低。

## Risks / Trade-offs

- [相对图片链接可能被 `rehype-harden` 清洗掉] → 先做一次最小验证；若被拦截，在传给 Streamdown 前把相对链接改写为占位 http(s) 形式（保留文件名映射），在 `img` 覆盖中还原为鉴权请求。
- [Streamdown 动态类名不被 Tailwind 扫描，样式缺失] → 照搬 opencode-qa 的 `@source` 与 utility 补丁，构建后人工核对表格/代码块/mermaid 外观。
- [mermaid/katex/shiki 增加前端体积] → mermaid 懒渲染；本次接受体积，后续可对插件做动态 import 优化。
- [多图时逐张 blob 请求与对象 URL 泄漏] → 按 `(kbId, conceptId, name)` 缓存，组件卸载统一 `revokeObjectURL`。
- [git-lfs 未 smudge，资产文件是 LFS 指针文本] → 读取时检测 `version https://git-lfs` 前缀，返回未找到或占位，避免把指针当图片返回。
- [概念 ID 含斜杠/点号导致 URL 解析问题] → 统一用查询参数并 `encodeURIComponent`，不走路径段。

## Migration Plan

- 纯增量：先部署后端路由（旧前端不受影响），再发布前端。
- 回滚：移除 `concepts` 路由注册与前端预览入口即可；无数据迁移、无 bundle 变更。
- 需要 `git-lfs` 才能在预览中看到图片，属既有部署前提，不新增依赖。

## Open Questions

- 无。图片鉴权、渲染栈、路由形态均已在上面确定；渲染清洗对相对链接的影响在实现首步验证（见 tasks）。
