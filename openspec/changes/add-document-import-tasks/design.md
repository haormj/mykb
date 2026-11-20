# Design

## Context

`add-knowledge-base-foundation` 已提供数据库、身份、知识库注册与库级鉴权，知识库各自拥有本地 git 仓库。现阶段导入只有 CLI，本变更补上浏览器上传、以数据库为准的任务状态机，以及文档列表。See `proposal.md - Why`.

## Goals / Non-Goals

**Goals:**
- 用户上传 Markdown/zip 即可把文档导入当前知识库的 `raw/`。
- 导入过程可观察：任务状态、计数、错误、时间戳落库。
- 同一知识库串行写入，避免 git 工作副本竞争。
- 文档页可浏览已导入文档及其来源任务。

**Non-Goals:**
- 不做语雀/Confluence/Git 等远程数据源（后续变更）。
- 不做跨进程分布式任务队列（测试期单进程）。
- 不长期保存上传原文件。

## Decisions

### 1. 任务表

```
import_tasks
  id UUID pk
  kb_id UUID fk knowledge_bases
  source_type text not null              -- 'upload'
  source_config jsonb not null           -- {files:[{name,size}], total_bytes}
  status text not null                   -- queued|running|succeeded|partial|failed|cancelled
  total int not null default 0
  added int not null default 0
  updated int not null default 0
  skipped int not null default 0
  failed int not null default 0
  error text null
  created_by UUID fk users
  created_at, started_at, finished_at
  INDEX (kb_id, status, created_at)
```

状态机与能力矩阵一致：路由写操作要求 editor；取消他人任务要求 admin。

### 2. 上传与临时目录

- 接口 `POST /kbs/{kb_id}/import-tasks`（multipart）。
- 允许 `.md`、`.markdown`、`.zip`；单请求大小上限（默认 50MB）由配置控制。
- 临时目录 `MYKB_KB_ROOT/.tmp/<task_id>/`；zip 解包需防路径穿越（拒绝绝对路径与 `..`）并限制解压条目数/总大小防 zip bomb。
- 任务进入终态后删除临时目录（`finally` 保证）。

### 3. 执行模型：单进程内 worker + per-KB 串行

- FastAPI 进程内维护 `dict[kb_id, asyncio.Lock]`，同库任务串行；不同库并行。
- 提交任务后由后台任务消费；数据库状态是唯一事实源，不用内存队列承载状态。
- 单进程假设：uvicorn 以 `--workers 1` 运行；多进程会破坏内存锁，留作后续换外部队列。
- 启动钩子把残留 `running` 扫描并置为 `failed`，避免永久卡住。
- git 写入（commit、可选 push）与审核合并在同一 per-KB 锁下，避免工作副本交错。

### 4. 连接器复用

- 新增 `upload` 来源适配：把临时目录交给现有 Markdown 目录连接器逻辑，复用 `BaseConnector.normalize` 产出 OKF 概念。
- 逐条目处理以支持 `partial`：单条失败累加 `failed` 并继续，整体异常才 `failed`。
- 复用现有 `Importer` 的增量状态思路，但把计数回写到 `import_tasks`。

### 5. 接口

```
POST   /kbs/{kb_id}/import-tasks        multipart -> 创建任务
GET    /kbs/{kb_id}/import-tasks        任务列表
GET    /kbs/{kb_id}/import-tasks/{id}   任务详情
POST   /kbs/{kb_id}/import-tasks/{id}/cancel
GET    /kbs/{kb_id}/documents           raw 文档 + 来源任务
```

所有接口经 `require_kb_role`：上传/取消自己=editor，取消他人=admin，查看=viewer。

## Risks / Trade-offs

- **单进程 worker** → 多 worker/多实例下并发失控；缓解：强制 `--workers 1`，并在文档与配置中标注，后续换外部队列。
- **zip bomb / 路径穿越** → 磁盘或越界写；缓解：解压前校验条目数与总大小、拒绝可疑路径。
- **大文件占用磁盘** → 缓解：大小上限 + 终态清理临时目录。
- **任务中途进程崩溃** → 缓解：启动时把 `running` 置 `failed`，用户可重试。
- **与审核合并并发写同一仓库** → 缓解：共用 per-KB 锁。

## Migration Plan

1. Alembic 新增 `import_tasks` 表并执行 `upgrade head`。
2. 配置上传大小上限与临时目录，确认 `MYKB_KB_ROOT` 可写。
3. 上线任务接口、worker 与文档接口；前端加文档页与导入弹窗。
4. 回滚：回退应用；保留 `import_tasks` 表（不影响旧版本），必要时清理临时目录。

## Open Questions

- 上传大小上限的具体默认值按部署磁盘容量再定。
- 是否需要保留导入原始文件的开关（审计/重放）留待真实需求出现再加。
