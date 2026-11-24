---
type: guide
title: 开发、配置与测试
description: mykb 的本地开发环境、环境变量与配置项、数据库迁移与管理员引导、Makefile 与开发脚本、后端 pytest 与前端 vitest、lint/typecheck/build，以及单进程任务执行器等运行约束。
tags: [operations, development, testing, configuration, migrations, tooling]
verified:
  - by: openwiki/0.9.0
    at: 2026-11-24T04:03:55.323Z
sources:
  - id: openwiki-source-ebee543967c6f3e7a101e271
    resource: repo://alembic.ini
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-a41ded727f97fd17b9db4917
    resource: repo://migrations/env.py
  - id: openwiki-source-c58354beb32ada23dd97dc70
    resource: repo://migrations/versions/0001_platform_foundation.py
  - id: openwiki-source-c2e93e7db98a74825ed48d18
    resource: repo://migrations/versions/0006_publish_tasks.py
  - id: openwiki-source-303b9ed2b5ad3d75abab2860
    resource: repo://mykb/api/app.py
  - id: openwiki-source-58aae222af55e2808de9efbf
    resource: repo://mykb/config.py
  - id: openwiki-source-f58733c2390c5aa1f016da2e
    resource: repo://mykb/db/bootstrap.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-a5928e7ee39885995efdc170
    resource: repo://scripts/dev.sh
  - id: openwiki-source-8a970789f677d5263e7c7409
    resource: repo://scripts/seed_demo.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-a50f994a00880fa45106d7a3
    resource: repo://tests/helpers.py
generated: { by: "opencode", at: "2026-11-24T04:03:55.323Z" }
---

# 开发、配置与测试

mykb 由 Python 后端（FastAPI + SQLAlchemy + Alembic）和 Vite/React 前端组成。本地开发通过 `uv` 安装后端依赖、`npm` 安装前端依赖，用 Makefile 统一常用命令。本文覆盖环境准备、配置、迁移、启动、测试与已知工具坑。

## 环境要求

- Python 3.11+（推荐 3.12）
- Node.js 18+
- Postgres 14+（测试用 SQLite）
- `uv`（后端依赖安装）
- `git-lfs`（导入含图片的 `.docx` 时必需；纯 Markdown 部署可不装）

`pyproject.toml` 声明运行依赖（fastapi、uvicorn、pydantic、PyYAML、httpx、SQLAlchemy、alembic、psycopg、PyJWT、bcrypt、cryptography、python-multipart）与 dev 依赖（pytest、pytest-asyncio、mypy、ruff、types-PyYAML）。

## 配置项

`load_settings` 从环境读取配置；缺失 `DATABASE_URL`、`JWT_SECRET`、`MYKB_SECRET_KEY` 时启动直接报错（`mykb/config.py:70`）。主要变量：

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 是 | 如 `postgresql+psycopg://mykb:mykb@localhost:5432/mykb` |
| `JWT_SECRET` | 是 | JWT 签名密钥 |
| `MYKB_SECRET_KEY` | 是 | 加密 git 凭据的密钥 |
| `MYKB_KB_ROOT` | 否 | 知识库根目录，默认 `~/.mykb/kbs` |
| `TOKEN_EXPIRES_DAYS` | 否 | 登录令牌有效期，默认 7 |
| `MYKB_UPLOAD_MAX_BYTES` / `MYKB_UPLOAD_MAX_ZIP_ENTRIES` | 否 | 上传总大小 / zip 条目上限 |
| `MYKB_PARSER_URL` / `_TIMEOUT` / `_TIER` / `_CONCURRENCY` / `_TOKEN` | 导入 docx 时 | 内部转换 sidecar 端点、超时、档位、并发与 token |
| `MYKB_CONVERSION_MAX_ASSETS` / `_MAX_ASSET_BYTES` / `_MAX_MARKDOWN_BYTES` | 否 | 单文档资产数量、资产大小、markdown 大小上限 |
| `MYKB_KB_ASSET_QUOTA_BYTES` | 否 | 每个知识库资产总量上限，默认 512 MiB |
| `MYKB_EXTRACTION_ENABLED` | 否 | 导入后是否自动提取，默认 `true` |
| `MYKB_WEKNORA_URL` / `_KEY` / `_TENANT_ID` / `_TIMEOUT` / `_RETENTION` / `_EMBEDDING_MODEL_ID` | 配 WeKnora 时 | 外部检索后端与发布配置 |
| `MYKB_LLM_BASE_URL` / `_API_KEY` / `_MODEL` | 否 | OpenAI 兼容提取端点；未配置用离线 FakeLLM |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 引导时 | 首个平台管理员 |

数值型配置由 `_int`/`_positive_int`/`_float` 校验，非法值抛 `ConfigError`（`mykb/config.py:77`）。`Settings` 还派生 `.tmp`、`.pending`、`.cache/parse` 等路径属性（`mykb/config.py:48`）。

## 数据库迁移与引导

- 迁移用 Alembic，脚本位于 `migrations/versions`，按域拆分为 `0001_platform_foundation` … `0006_publish_tasks` 的线性链。
- `migrations/env.py` 从 `DATABASE_URL` 读取连接串（覆盖 `alembic.ini` 的默认值），并 `from mykb.db import models` 注册全部表；SQLite 下启用 `render_as_batch`。
- `make migrate` 执行 `alembic upgrade head`。
- `make bootstrap` 运行 `mykb.db.bootstrap`：幂等创建 `admin`/`user` 角色，并在提供 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 时创建首个管理员（已存在则跳过，不覆盖）。引导目标是 Postgres 时需先迁移。

## Makefile 目标

| 目标 | 作用 |
| --- | --- |
| `make setup` | `uv venv` + `uv pip install -e ".[dev]"` + 前端 `npm install` |
| `make migrate` | 对 `DATABASE_URL` 执行 `alembic upgrade head` |
| `make bootstrap` | 创建角色与管理员 |
| `make backend` | 仅启动后端 uvicorn（`--reload`，:8000） |
| `make frontend` | 仅启动 Vite（:5173） |
| `make dev` | 用 `scripts/dev.sh` 同时启动前后端 |
| `make test` / `make lint` / `make typecheck` / `make check` | 后端测试 / ruff / mypy / 三者串联 |
| `make build` | 前端生产构建 |
| `make seed` | 生成 CLI 演示 bundle（见下方注意事项） |
| `make stop` / `make clean` | 停止 8000/5173 进程 / 删除 `.venv`、`node_modules`、`dist`、`.npm-cache` |

`make backend` 和 `make dev` 会透传 `MYKB_WEKNORA_*`、`MYKB_LLM_*` 等环境变量。后端固定单进程（uvicorn 默认），因为任务执行器是进程内的。

## 开发启动脚本

`scripts/dev.sh` 要求 `.venv` 与 `frontend/node_modules` 已存在，并强制要求 `DATABASE_URL`/`JWT_SECRET`/`MYKB_SECRET_KEY`。它用 job control 把后端与前端各自放入独立进程组，`Ctrl-C` 时通过 `kill -- -PID` 杀掉整棵进程树（含 uvicorn reloader 与 vite）（`scripts/dev.sh:1`）。端口可用 `BACKEND_PORT`/`FRONTEND_PORT` 覆盖。

前端 `vite.config.ts` 把 API 前缀代理到 `127.0.0.1:8000`，因此前端只需同源调用 `/kbs`、`/eval` 等。

## 后端测试

- 测试入口：`make test` → `pytest tests/ -q`；`pyproject.toml` 配置 `testpaths=["tests"]`、`asyncio_mode="auto"`。
- `tests/conftest.py` 在导入期设置临时 SQLite 与 KB 根目录的环境默认值（因为 `mykb.api.app` 在模块级 `app = create_app()`），并为每个测试提供 `app`（临时 SQLite + `create_tables=True` + bootstrap 一个 `root` 管理员）与 `client`（`TestClient`）fixture。
- 测试使用临时 SQLite，**不依赖 Postgres**；SQLite 连接开启外键约束。
- `tests/helpers.py` 提供 `auth`、`register`、`login`、`create_kb`、`publish_current` 等辅助；`publish_current` 直接调用 `SnapshotPublisher` 以便在测试中发布快照。
- 共 22 个测试模块，覆盖身份/授权、知识库、导入与转换、LFS/gitops、提取与评审、OKF 模型/校验、检索后端与 WeKnora、评测、维护与平台基础。

## 前端测试与检查

- `cd frontend && npm test`（vitest）覆盖纯逻辑：`pages/kb/context.test.ts`、`lib/tree.test.ts`、`lib/markdown.test.ts`。
- `npm run build` 先 `tsc --noEmit` 再 `vite build`，因此类型检查是构建的一部分。
- 组件/页面没有端到端测试。

## Lint 与类型检查

- `make lint`：`ruff check mykb tests`，行宽 100，忽略 `B008`（FastAPI 依赖默认参数写法）。
- `make typecheck`：`mypy mykb`。
- `make check`：`lint + typecheck + test`。

## 运行约束

- **单进程任务执行器**：导入、提取、发布都在进程内 `ThreadPoolExecutor` 中执行，多 worker/多实例会破坏串行与恢复假设，需换成外部队列。
- 应用启动会修正上次残留的 `running` 导入任务与 `processing` 提取项，因此重启是安全的但不保留进行中的内存任务。
- 检索后端默认是进程内内存引擎（重启后快照丢失，需重新发布）；生产应配置 WeKnora。

## 已知工具坑

`scripts/seed_demo.py` 仍 `from mykb.evaluation.evalset import EvalCase, EvalSetManager`，但当前 `mykb/evaluation` 只有 `runner.py`、`store.py`、`types.py`，不存在 `evalset` 模块。因此 `make seed` 会因导入失败而报错。评测已改为平台级 Postgres 存储，这个脚本需要在接入新 API 后重写；在此之前不要把它当作可用的演示入口。

## 相关页面

快速上手步骤见 [快速开始](../quickstart.md)，架构背景见 [系统架构总览](../architecture/overview.md)，知识库与 git 的运维细节见 [知识库生命周期与 Git 仓库](../kb/knowledge-base-lifecycle.md)。
