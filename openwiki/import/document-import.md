---
type: concept
title: 文档导入与导入任务
description: mykb 的上传导入链路：导入任务创建、文件与 zip 安全校验、临时暂存与清理、连接器框架、任务状态机、按库串行执行、取消与重启恢复，以及导入到待审提取项的交接。
tags: [import, upload, tasks, connectors, state-machine, workflow]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-cfcce8b424790f15abe688d1
    resource: repo://mykb/api/routes/import_tasks.py
  - id: openwiki-source-df92cfe223c905dc7240a8ec
    resource: repo://mykb/connectors/base.py
  - id: openwiki-source-8805dad5c38ed9b8b3af0f16
    resource: repo://mykb/connectors/sync.py
  - id: openwiki-source-10f3b96a1f256e4dc80e11d7
    resource: repo://mykb/connectors/upload.py
  - id: openwiki-source-c0c5611179789fbd7bd801e6
    resource: repo://mykb/conversion/base.py
  - id: openwiki-source-e505b7019d6a17328bbf6e7c
    resource: repo://mykb/extraction/queue.py
  - id: openwiki-source-5bf5447fc72bad3022b28450
    resource: repo://mykb/extraction/staging.py
  - id: openwiki-source-10133604e05abac5ade9afe0
    resource: repo://mykb/importing/service.py
  - id: openwiki-source-1404ac86826fd58da7fdbe4d
    resource: repo://tests/test_document_import.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 文档导入与导入任务

导入是把用户上传的 Markdown/docx/zip 变成一个待评审的源文档的入口。每次上传创建一个持久化的 `ImportTask`，后台 worker 在按知识库的锁内逐个转换文档、生成 `ExtractionItem` 并暂存，随后交由提取流水线生成文档级 MR。原始上传文件不持久化。本文说明这条链路的组成与状态。

## 入口与会话

`POST /kbs/{kb_id}/import-tasks` 要求 editor 权限，接收 multipart `files`（`mykb/api/routes/import_tasks.py:39`）：

1. 生成 `task_id`，读取所有上传文件字节。
2. `prepare_upload` 校验并暂存到 `MYKB_KB_ROOT/.tmp/<task_id>`，失败抛 `UploadError` → 400。
3. 落库一条 `status="queued"` 的 `ImportTask`，`source_config` 记录文件名与总字节数。
4. 把 `run_import_task` 提交到共享线程池，立即返回 201 与任务负载。

列表 `GET`、详情 `GET /{task_id}` 要求 viewer，取消 `POST /{task_id}/cancel` 要求 editor。

## 上传校验与安全

`prepare_upload` 对每个文件（`mykb/importing/service.py:95`）：

- 取 basename 作为安全名，拒绝空名；
- 后缀必须在 `SUPPORTED_SUFFIXES ∪ {".zip"}` 内，否则报“不支持的类型”；
- 累计大小不得超过 `MYKB_UPLOAD_MAX_BYTES`（默认 50 MiB），否则报超限；
- `.zip` 走 `safe_extract_zip`，其它直接写盘到任务临时目录。

`safe_extract_zip` 是安全重点（`mykb/importing/service.py:57`）：

- 条目数不得超过 `MYKB_UPLOAD_MAX_ZIP_ENTRIES`（默认 2000）；
- 拒绝绝对路径、含 `..` 的路径、以及首段带冒号（Windows 盘符）的路径；
- 只解压允许的后缀，其它条目忽略；
- 解压时按 64 KiB 分块累计实际字节，超过 `MYKB_UPLOAD_MAX_BYTES` 即中止（防 zip bomb）。

任何异常都会删除整个临时目录并向上抛 `UploadError`。测试 `test_upload_zip_and_reject_traversal` 固定了路径穿越拒绝行为。

## 临时暂存与清理

- 上传内容暂存在 `.tmp/<task_id>`，任务进入终态后由 `finally: shutil.rmtree(temp_dir)` 删除（`mykb/importing/service.py:378`）。
- 转换后的概念与资产暂存在仓库外的 `.pending/<item_id>`（提取项级别），由 `stage_concept` 写入（`mykb/extraction/staging.py:26`）。仓库只保留最终转换后的 markdown 与派生资产。
- 任务被取消或致命失败时，未处理项的 `.pending` 会被清理。

## 连接器框架

导入使用两层连接器抽象（`mykb/connectors/base.py:1`）：

- **sync 阶段**：从来源拉取原始项，返回 `RawItem`（文本）或 `RawDocument`（字节）。`RawItem.fingerprint()` 是内容的 SHA-256，用于增量同步。
- **normalize 阶段**：把原始项包装成 OKF 源概念。

`UploadDirConnector` 只做 sync：递归读取任务临时目录中后缀受支持的文件，产出 `RawDocument`（含 key、name、bytes、mime、suffix），不在这里做文本解码或转换（`mykb/connectors/upload.py:44`）。这保证二进制文档不会经过文本解码器。

`MarkdownDirConnector` 是另一个连接器，面向本地目录树，sync 时剥离已有 frontmatter 并生成 `RawItem`，供 CLI 导入场景使用。连接器通过 `register_connector` 注册、`get_connector` 解析（`mykb/connectors/registry.py`）。`Importer` 负责增量行为：按连接器保存每个 key 的 fingerprint 与产出概念 id，未变更的源在重跑时跳过（`mykb/connectors/sync.py:51`）。

平台 HTTP 导入走的是 `run_import_task`（带转换与提取），与 CLI 的 `Importer` 直接写 raw 是两条路径。

## 任务执行与串行

`run_import_task` 在按知识库的锁内运行（`mykb/importing/service.py:242`）：

1. 加载任务与知识库；库不存在则任务 `failed`。
2. 获取该库的锁后刷新任务，若状态已不是 `queued`（例如被取消）则直接返回。
3. 置 `running`，记录 `started_at`，用 `UploadDirConnector` 读取临时目录得到文档列表，写入 `total`。
4. 逐个文档调用 `_stage_document`：转换 → 改写资产链接 → 资产/LFS/配额检查 → 构建源概念 → 与已有 `x-original-sha256` 比对跳过 → 生成 `add`/`modify` 提取项并暂存。
5. 每个文档后检查任务是否被取消；取消则停止。
6. 汇总状态并清理，最后在成功路径调用 `process_pending` 触发提取。

同一知识库的导入串行、不同库可并行，由 `app.state.kb_locks` 与 `kb_locks_guard` 实现（`test_same_kb_imports_are_serialized`）。导入任务执行器是进程内的，因此后端必须单进程运行。

## 任务状态机

`ImportTask.status` 的流转：

```
queued → running → succeeded | partial | failed | cancelled
                              └→ queued-for-review → reviewing → merged | rejected
```

- 转换阶段：`running` 后若无排队项且无失败 → `succeeded`；无排队项但有失败 → `failed`；有排队项且有失败 → `partial`；有排队项且无失败 → `queued-for-review`；转换服务致命不可用 → `failed`（`mykb/importing/service.py:314`）。
- 评审阶段：提取项状态经 `refresh_import_task_status` 聚合为 `queued-for-review`/`reviewing`/`merged`/`rejected`（`mykb/extraction/queue.py:137`）。

注意 `failed`/`cancelled` 的导入任务不会被后续提取项聚合覆盖。

## 取消

`POST /{task_id}/cancel`（`mykb/api/routes/import_tasks.py:114`）：

- 只有任务创建者、平台管理员或知识库 admin/owner 可取消；
- 终态任务不能再取消（400）；
- 置任务 `cancelled`，对未进入 `merged/rejected/failed` 的提取项删除其分支、清理 `.pending` 并标记 `rejected`。

worker 在循环每步刷新任务，发现 `cancelled` 即停止处理剩余文档。

## 重启恢复

应用启动时 `mark_stale_running_failed` 把上次残留的 `running` 任务标记为 `failed`（错误“interrupted by service restart”）（`mykb/importing/service.py:141`）。测试 `test_restart_marks_running_as_failed` 覆盖该行为。提取项层面则由 `recover_processing` 把残留 `processing` 重置为 `queued`。

## 导入到评审的交接

导入阶段**不直接写主干**。每个文档只做两件事：生成 `ExtractionItem`（含 `concept_id`、`action`、`source_hash`、`title`）和把概念/资产暂存到 `.pending`。真正的 raw 写盘、知识提取与分支构建由提取 worker 完成，见 [AI 知识提取流水线](../extraction/knowledge-extraction.md) 与 [文档级评审与合并](../extraction/review-workflow.md)。

删除源文档是另一条入口：`DELETE /kbs/{kb_id}/documents/{concept_id}` 不经过导入任务，直接创建 `action=delete` 的提取项并触发 `process_pending`。

## 失败与幂等

- 单条转换失败只计 `failed` 并继续；致命服务错误中止整个任务。
- 同一源内容（`x-original-sha256` 相同）重复导入会被跳过并计 `skipped`，避免无意义 MR。
- 原始上传文件不持久化，因此失败后需要重新上传以重试。

## 代表测试

`tests/test_document_import.py` 覆盖 Markdown 上传生成 raw、zip 与路径穿越拒绝、不支持类型与超限、取消排队任务、重启标记失败、权限与跨库隔离、远程推送、同库串行、docx 转换与资产溯源、无解析器时 partial、解析器不可用整任务失败、混合 zip、资产配额失败保留已有内容、docx 资产以 LFS 指针提交。
