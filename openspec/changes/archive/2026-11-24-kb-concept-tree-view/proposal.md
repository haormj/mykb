# Proposal

## Why

知识库的「文档」与「知识」页面当前用扁平表格逐条列出概念。当概念按连接器或主题形成嵌套目录（如 `raw/upload/2024/...`、`knowledge/topics/billing/...`）时，扁平列表丢失目录层次，文件一多就难以定位和连续翻阅。目录结构本身已经存在于概念标识（concept_id）中，只是没有在界面上呈现。

## What Changes

- 将「文档」与「知识」页的概念列表改为**目录树**：按 concept_id 的路径层级组织文件夹与文件节点，同一层内目录在前、文件在后，文件名按自然序排序。
- 树节点展示概念标题，目录节点展示其下文件计数；完整概念路径在悬停提示与预览中可见。
- 选择文件节点时，沿用现有抽屉预览展示正文；原表格中的元数据（文档的来源与导入任务；知识的状态、验证与血缘来源）移入预览抽屉展示。
- 「文档」页保留导入入口、待审变更 MR 与导入任务两张表；文档删除操作移入预览抽屉，仍生成待审删除变更。
- 支持按标题或路径过滤树；数据刷新时保留展开与选中状态，选中项消失时关闭预览。
- 后端列表接口与预览接口保持不变，仅调整前端呈现方式。

## Capabilities

### New Capabilities

- `knowledge-browsing`: 以目录树浏览知识库 raw 与 knowledge 两个层级的概念，涵盖树结构推导、节点排序、目录计数、过滤、展开/选中状态以及选中后的预览入口。

### Modified Capabilities

（无：`document-import` 的文档列表接口与 `concept-preview` 的预览入口/渲染行为均保持不变，本次只改变前端呈现形态，需求层面的对外契约未变。）

## Impact

- 前端：改造 `frontend/src/pages/kb/DocumentsTab.tsx` 与 `KnowledgeTab.tsx`；新增 `frontend/src/lib/tree.ts` 及其单元测试；`frontend/src/services/api.ts` 的类型与接口调用不变。
- 后端：无改动。复用现有 `GET /kbs/{kb_id}/documents`、`GET /kbs/{kb_id}/knowledge`、`GET /kbs/{kb_id}/concepts/content` 与资产接口。
- 不影响导入、评审、检索、发布与存储行为；不新增依赖。
