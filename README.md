# mykb

企业知识管理平台：以 **Postgres 管理平台元数据**，以 **每个知识库一个 git 仓库（OKF bundle）承载内容**。

```
Postgres                          git repo per knowledge base
  users / roles / tokens            raw/        源数据（文档）
  knowledge_bases / kb_members      knowledge/  业务知识（审核后）
  (import_tasks, next phase)        evals/      评测集
```

## 能力

- 本地账号体系：注册、登录、登出、当前用户；JWT + 服务端 token 白名单；预留 SSO 字段。
- 两级授权：平台角色（`admin` / `user`）+ 知识库成员角色（`owner` / `admin` / `editor` / `viewer`）。
- 知识库注册：名称/slug/本地路径唯一；创建时初始化独立 git 仓库与 OKF 布局；远程仓库可选。
- 知识库作用域接口：检索、评测、草稿审核均在 `/kbs/{kb_id}` 下。

## 环境要求

- Python 3.11+（推荐 3.12）
- Node.js 18+
- Postgres 14+
- `uv`（后端依赖安装）
- `git-lfs`（导入含图片的 `.docx` 时必需；仅 Markdown 的部署可不装）

## 配置

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 是 | 如 `postgresql+psycopg://mykb:mykb@localhost:5432/mykb` |
| `JWT_SECRET` | 是 | JWT 签名密钥（建议 ≥32 字节） |
| `MYKB_SECRET_KEY` | 是 | 加密知识库 git 凭据的密钥 |
| `MYKB_KB_ROOT` | 否 | 本地知识库根目录，默认 `~/.mykb/kbs` |
| `TOKEN_EXPIRES_DAYS` | 否 | 登录令牌有效期，默认 7 |
| `MYKB_UPLOAD_MAX_BYTES` | 否 | 单次上传大小上限，默认 50 MiB |
| `MYKB_UPLOAD_MAX_ZIP_ENTRIES` | 否 | zip 条目数上限，默认 2000 |
| `MYKB_PARSER_URL` | 导入 docx 时 | 内部转换服务的解析端点；为空时仅支持 Markdown |
| `MYKB_PARSER_TIMEOUT` | 否 | 单文档转换超时秒数，默认 60 |
| `MYKB_PARSER_TIER` | 否 | 解析档位，默认 `flash` |
| `MYKB_PARSER_CONCURRENCY` | 否 | 并发转换数，默认 2 |
| `MYKB_PARSER_TOKEN` | 否 | 调用内部转换服务的 Bearer token |
| `MYKB_CONVERSION_MAX_ASSETS` | 否 | 单文档图片数量上限，默认 100 |
| `MYKB_CONVERSION_MAX_ASSET_BYTES` | 否 | 单文档资产总大小上限，默认 20 MiB |
| `MYKB_CONVERSION_MAX_MARKDOWN_BYTES` | 否 | 单文档 markdown 大小上限，默认 10 MiB |
| `MYKB_KB_ASSET_QUOTA_BYTES` | 否 | 每个知识库资产总量上限，默认 512 MiB |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 引导时 | 首个平台管理员 |

缺失必需变量时服务启动会直接报错。

## 快速开始

```bash
# 1. 安装依赖
make setup

# 2. 准备 Postgres 数据库（示例）
createdb mykb

# 3. 建表
export DATABASE_URL=postgresql+psycopg://mykb:mykb@localhost:5432/mykb
export JWT_SECRET=change-me-to-a-long-random-secret
export MYKB_SECRET_KEY=change-me-too
make migrate

# 4. 创建平台角色与管理员
make bootstrap            # 默认 admin / admin123，可用 ADMIN_USERNAME/ADMIN_PASSWORD 覆盖

# 5. 启动
make dev                  # 后端 :8000 + 前端 :5173
```

前端登录后进入「知识库」列表，新建知识库即可。系统**不预置任何默认知识库**。

## 知识库与 git

- 每个知识库在 `MYKB_KB_ROOT/<slug>-<id前8位>/` 下拥有独立 git 仓库。
- 新建时 `git_url` 可选：
  - 留空：仅本地 git 管理（**内容只在这台机器**）。
  - 填写：克隆远程、初始化 OKF 布局并推送；远程必须是服务端可访问的地址。
- 已存在的本地知识库可由 owner 在后续补绑远程，当前只允许绑定**空远程**。
- 服务端使用 `oauth2:<token>@host` 形式注入 HTTPS 凭据；提交作者固定为 `mykb-agent`。
- 仓库初始化会写入图片类型的 `.gitattributes` 并执行 `git lfs install --local`；绑定 HTTPS 远程时会探测其 LFS 能力，不支持则拒绝绑定。
- 备份知识库时必须包含 `.git/lfs/objects`（或依赖远程 LFS 对象），否则恢复后图片只剩指针；本地空间可用 `git lfs prune` 清理不再引用的对象。

## 文档导入

- 在知识库「文档」页点击「导入文档」，上传 Markdown（`.md` / `.markdown`）、Word（`.docx`）或包含它们的 zip。v1 不支持 `.pdf` 与旧版 `.doc`。
- Markdown 直通；`.docx` 通过内部转换 sidecar 转为 markdown，默认 `flash` 档。未配置 `MYKB_PARSER_URL` 时仅 Markdown 可用，docx 条目失败并提示未启用。
- 转换产出的图片写入概念同名的 `<concept>.assets/` 目录，由 Git LFS 管理；本期只存储、不提供平台内预览。
- 原始上传文件（docx/md/zip）**不持久化**：上传内容暂存在 `MYKB_KB_ROOT/.tmp/<task_id>`，任务进入终态（成功、失败、取消）后删除。仓库只保留转换后的 markdown 与派生资产。
- 源数据 frontmatter 记录 `x-source-format`、`x-original-name`、`x-original-sha256`、`x-original-size`、`x-parsed-by`、`x-import-task`；`resource` 是逻辑来源标识，不承诺可回取。
- 每次上传创建一个持久化的导入任务，状态为 `queued → running → succeeded | partial | failed | cancelled`，计数与错误写回数据库。
- 单条转换失败只影响该条目（任务 `partial`）；转换服务未配置时该条目失败；转换服务不可达或鉴权失败时任务 `failed` 可重试，不写入半成品。
- 同一知识库的导入任务串行执行（不同库可并行），转换与写入完成后提交 git；配置了远程则一并推送。
- 服务重启时会把残留的 `running` 任务标记为 `failed`。
- 任务执行器是**进程内**的，因此后端必须以单进程运行（`--workers 1`，`make backend` 已是如此）；多 worker/多实例需要换成外部队列。

## 文档转换 sidecar

- 只允许部署在内部网络，容器**不得有出网**，并显式禁用 MinerU 的 `--remote`；模型与依赖必须预置在镜像内，禁止首次运行时下载。
- 镜像 tag 要固定；`x-parsed-by` 会记录 sidecar 返回的解析版本。
- 为容器设置 CPU/内存/进程数限额，并让 `MYKB_PARSER_CONCURRENCY` 不超过 sidecar 实际并发能力。
- sidecar 对外暴露一个归一化端点（`MYKB_PARSER_URL`）：
  - 请求：`multipart/form-data`，字段 `file`（原始文档）与 `tier`（解析档位）。
  - 响应：`{"markdown": "...", "title": "...", "parser_version": "...", "warnings": [...], "assets": [{"name": "img-1.png", "content_base64": "..."}]}`。
  - markdown 中以 `name` 引用图片；平台会将其改写为 bundle 内的 `.assets/` 相对路径。

## 主要接口

```
POST /auth/register | /auth/login | /auth/logout
GET  /auth/me
GET  /admin/users                      平台管理员
GET|POST /kbs
GET|PATCH|DELETE /kbs/{kb_id}
POST /kbs/{kb_id}/remote               owner 补绑远程
GET|POST|PATCH|DELETE /kbs/{kb_id}/members
POST /kbs/{kb_id}/members/{user_id}/transfer
GET  /kbs/{kb_id}/retrieve | /answer
POST /kbs/{kb_id}/index-sync           admin
GET|POST /kbs/{kb_id}/eval/*
GET  /kbs/{kb_id}/review/drafts|diff
POST /kbs/{kb_id}/review/approve       admin
GET  /kbs/{kb_id}/documents            viewer
GET  /kbs/{kb_id}/knowledge            业务知识只读投影
POST /kbs/{kb_id}/import-tasks         editor（multipart: files）
GET  /kbs/{kb_id}/import-tasks         列表/详情
POST /kbs/{kb_id}/import-tasks/{id}/cancel
```

旧的全局路由（`/retrieve`、`/eval/*`、`/review/*` 等）已移除，返回 404。

## 测试与检查

```bash
make test        # 后端测试（测试使用临时 SQLite，不依赖 Postgres）
make lint        # ruff
make typecheck   # mypy
make check       # lint + typecheck + test
make build       # 前端生产构建
cd frontend && npm test   # 前端权限逻辑测试
```

## 界面结构

应用外壳：左上角为平台名「企业知识管理平台」，顶部标题为「知识库」，左侧边栏保留一个「知识库」入口（在列表与详情页均保持高亮）。

登录后进入「知识库」大页面查看知识库列表，点击某个知识库进入其工作台：

```
/kbs/:kbId/documents   文档导入与导入任务
/kbs/:kbId/knowledge   业务知识（只读，含状态与血缘）
/kbs/:kbId/evals       评测集与运行
/kbs/:kbId/review      草稿审核（admin+）
/kbs/:kbId/scores      分数看板
/kbs/:kbId/settings    基础设置、远程仓库、成员管理（admin+）
```

- viewer 只读；editor 可导入、起草、评测；admin 可审核、设置与成员管理；owner 还可删除/转让/修改远程。
- 深链访问无权知识库或页面会显示 403 提示。
