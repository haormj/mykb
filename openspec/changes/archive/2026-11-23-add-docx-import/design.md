# Design

## Context

见 `proposal.md`。当前上传链路（`mykb/importing/service.py`）用 `ALLOWED_EXTENSIONS = {".md", ".markdown", ".zip"}` 做白名单，zip 只收集 markdown 条目；`UploadDirConnector` 直接继承 `MarkdownDirConnector`，其 `sync()` 以 `read_text(encoding="utf-8")` 读取文件，`normalize()` 只是原样包 frontmatter。`RawItem.content_type` 已存在但未被使用（`mykb/connectors/base.py:30`）。`Bundle.write_concept` 只写 `.md`（`mykb/okf/bundle.py:99`）；`gitops.py` 全部是裸 `git` 子进程，仓库初始化不写 `.gitattributes`。

约束：转换只能走内部 sidecar、不产生外部调用；原始文档不持久化；v1 只做 `.docx`，PDF 后续扩展；图片用标准 Git LFS 保存。

## Goals / Non-Goals

**Goals:**

- `.docx` 能上传、转换并落为 OKF 源数据概念，图片资产随概念进入知识库 git 仓库。
- 转换实现可替换：后续加 PDF 只需新增 provider，不改编排链路。
- 来源可追溯：原件删除后仍能通过内容指纹与解析标识定位数据。
- 未配置/不可用 sidecar 时行为明确，且不影响现有 Markdown 导入。

**Non-Goals:**

- PDF、旧版 `.doc`、OCR、图片平台内预览（本期只存储不展示）。
- 历史文档重刷（原件不留，换解析器无法回溯重转）。
- 外部 SaaS 解析、多 worker 队列改造。

## Decisions

### D1. 转换独立成站，不塞进上传连接器

`sync` 只负责产出原始文件（key、原始文件名、字节、MIME），新增转换层产出 markdown，`normalize` 继续负责包 OKF frontmatter。这样二进制文件不再经过 `read_text`，也让 PDF 等新格式有统一入口。

备选：
- 在 `MarkdownDirConnector.sync` 里按扩展名分支转换 → 拒绝：同步阶段混合了 IO 与解析，二进制易错，扩展困难。
- 让 `UploadDirConnector` 重写 `normalize` 调解析库 → 拒绝：仍绕不开 sync 的文本读取，且 normalize 职责变混。

接口草案（实现位置见 tasks）：

```
RawDocument { key, name, data: bytes, mime }
Asset       { name, data: bytes }
ConversionResult { markdown, title, assets, producer, warnings }
DocumentConverter { supports(ext, mime) -> bool; convert(RawDocument) -> ConversionResult }
```

provider 选择：`.md/.markdown` 用 passthrough（保留原 frontmatter），`.docx` 用 MinerU HTTP provider。注册表按扩展名/MIME 路由，配置为空时候选集合只剩 passthrough。

### D2. sidecar 用同步 HTTP + 单条超时

通过 `httpx`（已是依赖）调用内部转换服务，按条目一次请求，设置 `MYKB_PARSER_TIMEOUT`；失败按 D7 归类。选同步而非 MinerU 异步 tasks API：导入任务本身已是异步的 `queued -> running`，编排层不需要再映射一层外部 job 状态；等出现超长文档再换异步接口。

备选：
- 进程内 `pip install mineru` → 拒绝：模型体积、依赖与升级节奏污染后端镜像和 `pydantic`/`fastapi` 版本。
- 外部 SaaS → 与"仅内部"约束冲突，排除。

新增配置：`MYKB_PARSER_URL`、`MYKB_PARSER_TIMEOUT`、`MYKB_PARSER_TIER`（docx 用 `flash`）、`MYKB_PARSER_CONCURRENCY`、可选 `MYKB_PARSER_TOKEN`。`MYKB_PARSER_URL` 为空 → 只启用 passthrough。

### D3. 版本固定与来源标记

sidecar 镜像 tag 固定，启动或首次调用读取其版本；写入 `x-parsed-by: mineru@<version>`。frontmatter 增加 `x-source-format`、`x-original-name`、`x-original-sha256`、`x-original-size`；`x-import-task` 保留。`resource` 维持 `upload://<task>/<name>`，定位为逻辑来源标识，规范中明确不可回取。

### D4. 资产布局与命名

```
raw/upload/<doc>.md
raw/upload/<doc>.assets/<序号>-<sha8><ext>
```

资产名由后端确定（序号 + 内容 hash + 白名单扩展名），不直接采用解析器返回的路径，避免不确定性和路径穿越。markdown 中改写为指向 `.assets/` 的相对链接。仅接受位图类型（png/jpg/jpeg/gif/webp）；其他类型记录 warning 并跳过该资产。鉴于本期没有资产读取路由，SVG 先不入库。

### D5. Git LFS 接入

- 仓库初始化（`init_local_repo`、`clone_or_init_with_remote`、`ensure_layout` 路径）写入 `.gitattributes`，覆盖图片扩展名，并在仓库执行 `git lfs install --local`。
- 提交前检测 `git-lfs` 可执行存在，缺失则导入失败并给出安装提示，避免二进制被当普通 blob 写入。
- push 沿用现有 `gitops.push`；LFS 对象随 push 传输。由于 `bind_remote` 只允许空远程，克隆期不会拉取历史 LFS 对象，暂不引入 `GIT_LFS_SKIP_SMUDGE`。
- `bind_remote` 增加远程 LFS 能力探测，不支持时拒绝绑定并说明原因。
- 备份口径包含 `.git/lfs/objects` 或远程 LFS；每库资产配额超限时按条目失败。

备选：独立对象存储（拒绝，违背"标准 Git LFS"决定且 bundle 不再自包含）；保留普通 blob（拒绝，仓库体积不可控）。

### D6. 原件不持久化与可追溯

任务终态删除上传临时目录（现有 `finally` 行为），不额外落盘原件。`x-original-sha256` 作为内容身份，可用于重复上传识别与解析结果缓存 key。解析缓存只存派生结果，放在 `MYKB_KB_ROOT/.cache/parse/<sha256>/`，与"不存原件"不冲突。

### D7. 失败语义与并发

- 上传阶段：类型不在白名单 → 400，提示允许类型。
- 单条转换失败（格式不支持、解析错误、产物超限）→ 该条 `failed`，任务最终 `partial`。
- sidecar 未配置或不可达、鉴权失败 → 任务 `failed`（可重试），已处理条目保留，未处理条目不写半成品。
- 转换在写概念前完成，产物校验通过后再落盘；落盘失败按条目失败处理。
- 用信号量把并发转换数限制到 `MYKB_PARSER_CONCURRENCY`；现有进程内线程池（`mykb/api/app.py:62`）与每库串行锁不变。

### D8. 前端与错误提示

`DocumentsTab.tsx` 的 `accept` 与说明改为 Markdown、`.docx`、zip；后端错误详情直接展示允许类型。列表接口不新增资产字段，保持现状。

## Risks / Trade-offs

- [MinerU 不同版本产物结构/命名变化] → 镜像 tag 固定，后端做确定性重命名，`x-parsed-by` 记录版本。
- [内部 Git 平台的 LFS 鉴权与 `oauth2:<token>@host` 不兼容] → 接入前先做 spike，必要时改用 `lfs.url` 或 extraheader；绑定远程前探测能力。
- [docx 版式/文本框/复杂表格丢失] → 明确 v1 以文本与常见表格为目标，warning 记录，不承诺版式还原。
- [LFS 对象持续增长] → 每库配额 + 文档化 `git lfs prune` 与备份要求。
- [长文档转换占用工作线程、拖慢同库任务] → 单条超时、并发信号量；后续可改异步 tasks API。
- [原件不留导致无法回溯重转] → 记录 hash 与解析版本，作为已知取舍写入规范；需要时再立变更。
- [图片入库但平台不可见] → 明确本期只存储不展示，避免被当作缺陷。

## Migration Plan

1. 现有知识库不需要数据迁移：历史上没有二进制资产，首次导入或下次仓库初始化时补写 `.gitattributes`。
2. 部署 sidecar：镜像内置模型、禁用 `--remote`、容器无出网、设置资源限额；后端安装 `git-lfs` 并做启动检测。
3. 配置 `MYKB_PARSER_*` 后灰度启用；未配置时退化为仅 Markdown。
4. 回滚：清空 `MYKB_PARSER_URL` 即回到 Markdown-only；已提交的 LFS 资产在装有 `git-lfs` 的环境仍可正常检出，无数据库迁移。

## Open Questions

- MinerU 对外端点的确切路径与响应结构以接入 spike 结果为准；它只影响 HTTP 适配器内部，不改变 D1/D2 的分层。
