# Proposal

## Why

知识库内容以 markdown 概念形式存放在 git bundle 中（`raw/` 为转换后的源数据，`knowledge/` 为业务知识），原始上传文档不持久化。目前平台只能列出文档与知识的标题、状态和来源，无法阅读正文，也无法看到转换产生的图片，评审 diff 也只能显示为纯文本。用户需要直观核对转换结果、阅读业务知识，因此要提供 markdown 预览。

## What Changes

- 新增按知识库读取单个概念正文的接口：raw 文档与业务知识各一个，权限沿用 `viewer`。
- 新增受保护的派生资产读取接口：只允许读取指定概念同名 `<concept>.assets/` 目录内的图片，拒绝路径穿越。
- 前端新增统一的 `MarkdownView` 组件，基于 Streamdown 渲染，启用 `code`、`mermaid`、`math`、`cjk` 插件，剥离 YAML frontmatter。
- 前端图片通过带 Bearer 的 `fetch` 获取后转 blob URL 渲染，解决 `<img>` 不携带 Authorization 的问题。
- 「文档」与「知识」两个标签页各增加「预览」入口，复用同一个 `MarkdownView`。
- 接入 Streamdown 所需样式与 Tailwind 扫描配置，并新增前端依赖（版本对齐 `../opencode-qa`）。

## Capabilities

### New Capabilities
- `concept-preview`: 读取并有权限地渲染知识库中的 raw 源数据概念与业务知识概念（markdown 正文 + 派生图片资产），供有查看权限的成员在平台内预览。

### Modified Capabilities
- （无：本次不改变既有能力的需求，仅为内容增加预览读取路径。）

## Impact

- 后端：`mykb/api/routes/documents.py`、`mykb/api/routes/knowledge.py`（或新增概念内容/资产路由），`mykb/okf/bundle.py`（读取概念正文与资产字节），`mykb/api/app.py`（注册路由）。
- 前端：新增 `MarkdownView` 组件；改造 `frontend/src/pages/kb/DocumentsTab.tsx`、`frontend/src/pages/kb/KnowledgeTab.tsx`；扩展 `frontend/src/services/api.ts`；调整 `frontend/src/index.css` 与 `frontend/package.json`。
- 依赖：新增 `streamdown`、`@streamdown/code`、`@streamdown/mermaid`、`@streamdown/math`、`@streamdown/cjk`、`katex`。
- 安全：资产接口须做路径穿越校验；markdown 渲染须清洗（Streamdown 默认 `rehype-harden`）；图片必须通过鉴权获取。
- 无数据库迁移，无 git bundle 布局变更。
