# Proposal

## Why

用户需要在知识库内"导入文档"，并能看到导入进度与结果。当前导入只有 CLI，没有任务记录、没有文档浏览页，也不支持从浏览器上传文件。本变更在第一阶段平台地基之上，补上以数据库记录为准的导入任务与文档页。

## What Changes

- 新增知识库「文档」能力：浏览 `raw` 层已导入文档，展示来源与所属导入任务。
- 新增「导入文档」入口：用户选择本地文件（Markdown / zip）上传，服务端解包到临时目录后经本地连接器归一化写入该知识库 `raw/`。
- 每次导入创建一个持久化导入任务，状态为 `queued / running / succeeded / partial / failed / cancelled`，记录计数、错误与时间戳。
- 同一知识库的导入任务串行执行，避免并发写同一 git 工作副本；进程内 worker 执行，状态以数据库为准，重启时将残留 `running` 转为 `failed`。
- 上传原文件不长期保留，仅保留归一化后的 `raw` 概念与任务记录；限制文件类型与大小。
- 新增任务列表/详情接口与文档列表接口（均按知识库鉴权）。

## Capabilities

### New Capabilities

- `document-import`: 通过上传本地文件创建导入任务、驱动连接器写入 `raw/`，并提供文档列表与任务状态查询。

### Modified Capabilities

- `knowledge-import`: 导入从"仅 CLI 指定目录"扩展为"用户上传触发的任务驱动导入"，并作为本地连接器来源之一。

## Impact

- **Backend**: 新增上传接口、导入任务模型与 per-KB 串行 worker、临时目录处理；`mykb/connectors` 增加上传来源适配。
- **Frontend**: 新增知识库「文档」页与「导入文档」弹窗，展示任务进度与结果。
- **Dependencies**: 文件上传解析（如 `python-multipart`、`zipfile`）。
- **Depends on**: `add-knowledge-base-foundation`（数据库、身份、知识库与库级鉴权）。
- **Follow-up**: `scope-features-to-knowledge-base`（设置/成员与其余页面迁入）。
