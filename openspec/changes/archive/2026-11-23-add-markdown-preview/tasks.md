# Tasks

## 1. 后端概念读取

- [x] 1.1 在 `mykb/okf/bundle.py` 增加读取单段资产的方法（由 `concept_id` 拆层级与相对路径、校验 `name` 为单段、`resolve()` 后限定在概念 `.assets/` 内、返回字节与按扩展名推断的 MIME，并检测 LFS 指针文本），用 pytest 覆盖正常读取、`..`/绝对路径/跨概念拒绝与指针检测
- [x] 1.2 新增 `mykb/api/routes/concepts.py` 的 `GET /kbs/{kb_id}/concepts/content?concept_id=`，返回 `{concept_id, level, title, body}`，用 `require_kb_role("viewer")` 鉴权；用 pytest 覆盖 raw 正文、knowledge 正文、非成员 403、概念不存在 404、不跨库
- [x] 1.3 在同路由新增 `GET /kbs/{kb_id}/concepts/asset?concept_id=&name=` 返回图片字节与 `Content-Type`，并在 `mykb/api/app.py` 注册路由；用 pytest 覆盖成功取图、未授权、缺失资产与穿越请求返回 404

## 2. 前端渲染基础

- [x] 2.1 在 `frontend/package.json` 增加 `streamdown`、`@streamdown/code`、`@streamdown/mermaid`、`@streamdown/math`、`@streamdown/cjk`、`katex`（版本对齐 `../opencode-qa`），安装后 `npm install` 成功且 `npm run build` 不因依赖缺失报错
- [x] 2.2 在 `frontend/src/index.css` 接入 Streamdown：`@source` 五个包、`@import "streamdown/styles.css"`、`katex` 样式、`:root` shadcn 变量与动态 utility 补丁，验证 `npm run build` 通过并肉眼确认表格/代码块样式正常
- [x] 2.3 新增 `frontend/src/components/MarkdownView.tsx`，用 Streamdown + `{ code, mermaid, math, cjk }` 渲染，含防御性 frontmatter 剥离与 `components.img` 带 Bearer 的 blob 加载（卸载 `revokeObjectURL`、按 `(kbId, conceptId, name)` 缓存）；把 frontmatter 剥离与资产名提取抽成纯函数并用 vitest 覆盖
- [x] 2.4 验证相对图片链接在 Streamdown 默认清洗下能保留并触发 `img` 覆盖；若被 `rehype-harden` 拦截，则改为渲染前把相对资产链接改写为占位 http(s) 地址再在 `img` 覆盖中还原，并确保渲染后图片可见

## 3. 前端接入页面

- [x] 3.1 在 `frontend/src/services/api.ts` 增加 `getConceptContent(kbId, conceptId)` 与 `fetchConceptAsset(kbId, conceptId, name)`（后者返回 `Blob` 且带 Bearer），验证 `tsc` 类型检查通过
- [x] 3.2 在 `frontend/src/pages/kb/DocumentsTab.tsx` 增加"预览"入口（抽屉），用 `MarkdownView` 展示 raw 正文；验证构建通过并手动打开含图片的 raw 文档可看到渲染正文与图片
- [x] 3.3 在 `frontend/src/pages/kb/KnowledgeTab.tsx` 增加"预览"入口（抽屉），复用 `MarkdownView` 展示业务知识正文；验证构建通过并手动打开知识可看到渲染正文

## 4. 集成验证

- [x] 4.1 运行 `make check`（ruff + mypy + pytest）与 `cd frontend && npm test && npm run build`，确认全部通过
- [x] 4.2 手动走查：有权限成员在文档页/知识页预览成功；非成员访问内容接口返回 403；`../` 资产请求返回 404

## Workflow follow-up

- 评审通过后归档该 change，并验证归档结果。
