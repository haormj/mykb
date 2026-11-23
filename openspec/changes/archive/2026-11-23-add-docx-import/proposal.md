# Proposal

## Why

当前文档导入只接受 Markdown（或包含 Markdown 的 zip），用户实际持有的 Word 等格式无法进入知识库。知识库需要把常见办公文档转换为 markdown 后入库，同时保持"原始文档不持久化、仓库只保存派生数据"的既有约束。

采用内部 sidecar 做格式转换，避免引入外部接口与数据出网；v1 先支持 Word（`.docx`），PDF 等其他格式留作后续扩展。

## What Changes

- 新增文档格式转换能力：本地上传的 `.docx` 交由内部 MinerU sidecar 转为 markdown；`.md`/`.markdown` 保持直通。
- 转换产物（markdown concept + 图片资产）写入知识库 git 仓库；图片资产使用标准 Git LFS 管理，原始文档（docx/md/zip）在任务结束后删除、不持久化。
- 上传白名单从 `.md`/`.markdown`/`.zip` 扩展为 `.md`/`.markdown`/`.docx`/`.zip`（zip 内同理）；`.pdf`、旧版 `.doc` 等暂不支持，返回明确错误。
- 源数据 frontmatter 增加转换与来源标记（`x-source-format`、`x-original-name`、`x-original-sha256`、`x-original-size`、`x-parsed-by`），`resource` 作为逻辑来源标识、明确不可回取。
- 转换按条目独立处理：单条解析失败计入 `failed` 并令任务为 `partial`；解析服务不可用令任务 `failed` 可重试，不写入半成品。
- 知识库仓库初始化/导入时配置 Git LFS（`.gitattributes`、`git lfs install --local`），并在绑定远程时校验远程 LFS 能力。
- **BREAKING**：`.pdf` 与旧版 `.doc` 仍不被接受（此前也仅支持 Markdown）；上传大小/条目限制沿用现有配置。

## Capabilities

### New Capabilities

- `document-conversion`: 定义文档转换为 markdown 的 provider 契约、支持的输入格式、转换来源标记、产物限额与失败语义；转换只允许通过内部 sidecar 完成，不调用外部接口。

### Modified Capabilities

- `document-import`: 上传类型白名单加入 `.docx`、导入产物包含图片资产、原始文档不持久化、新增资产数量与大小限制、失败语义细化。
- `knowledge-import`: 本地上传来源接入"转换"阶段，`.docx` 归一化为 OKF 源数据概念及其资产。
- `knowledge-storage`: raw 层允许由标准 Git LFS 管理的二进制资产，明确资产目录约定与每库配额，并声明资产为派生数据。

## Impact

- 后端：`mykb/importing/service.py`（上传校验、任务执行、临时文件清理）、`mykb/connectors/upload.py` 与 `mykb/connectors/markdown_dir.py`（同步产出原始字节、转换阶段）、新增解析 provider 模块、`mykb/okf/bundle.py`（资产写入）、`mykb/kb/gitops.py`（LFS 初始化与推送）、`mykb/config.py`（解析服务配置）、`mykb/api/routes/import_tasks.py`（类型错误与限额提示）。
- 前端：`frontend/src/pages/kb/DocumentsTab.tsx` 上传 accept 与提示文案；`frontend/src/services/api.ts` 不变。
- 部署：新增内部 MinerU sidecar（模型预置、禁 `--remote`、容器无出网、CPU/内存限额）；后端运行环境需安装 `git-lfs`。
- 存储：知识库 git 仓库新增 `.gitattributes` 与 `*.assets/` 资产目录；LFS 对象纳入备份口径。
- 依赖：无新增 Python 运行时依赖（复用 `httpx` 调 sidecar）；新增外部二进制/容器依赖 `git-lfs`、`mineru`。
- 兼容性：知识库内已有 `.md` 导入行为不变；未配置解析 sidecar 时仅 Markdown 可用，`.docx` 导入明确失败。
