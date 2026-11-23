PY := .venv/bin/python
NPM_CACHE := $(CURDIR)/.npm-cache
DATABASE_URL ?= postgresql+psycopg://mykb:mykb@localhost:5432/mykb
MYKB_KB_ROOT ?= $(HOME)/.mykb/kbs
JWT_SECRET ?= dev-insecure-change-me-please-use-32-bytes
MYKB_SECRET_KEY ?= dev-insecure-change-me
MYKB_WEKNORA_URL ?=
MYKB_WEKNORA_KEY ?=
MYKB_WEKNORA_TENANT_ID ?=
MYKB_WEKNORA_EMBEDDING_MODEL_ID ?=
MYKB_LLM_BASE_URL ?=
MYKB_LLM_API_KEY ?=
MYKB_LLM_MODEL ?=
ADMIN_USERNAME ?= admin
ADMIN_PASSWORD ?= admin123
BUNDLE ?= $(HOME)/.mykb/kb

.PHONY: help setup migrate bootstrap backend frontend dev test frontend-test typecheck lint check build stop clean

help:
	@echo "make setup      安装后端(uv)与前端(npm)依赖"
	@echo "make migrate    对 DATABASE_URL 执行 alembic upgrade head"
	@echo "make bootstrap  创建平台角色与管理员 (ADMIN_USERNAME/ADMIN_PASSWORD)"
	@echo "make dev        同时启动前后端（后端自动重载 + 前端 HMR）"
	@echo "make backend    仅启动后端 http://localhost:8000 (uvicorn --reload)"
	@echo "make frontend   仅启动前端 http://localhost:5173 (vite HMR)"
	@echo "make test       运行后端测试"
	@echo "make frontend-test  运行前端测试 (vitest)"
	@echo "make check      lint + typecheck + 测试"
	@echo "make build      构建前端生产包"
	@echo "make seed       生成 CLI 演示用独立 bundle（默认 $(BUNDLE)，不进入平台）"
	@echo "make stop       停止占用 8000/5173 的服务"
	@echo "make clean      删除 .venv / node_modules / dist"
	@echo ""
	@echo "必需环境变量: DATABASE_URL, JWT_SECRET, MYKB_SECRET_KEY"

setup:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[dev]"
	cd frontend && npm install --cache $(NPM_CACHE)

migrate:
	DATABASE_URL="$(DATABASE_URL)" $(PY) -m alembic upgrade head

bootstrap:
	DATABASE_URL="$(DATABASE_URL)" ADMIN_USERNAME="$(ADMIN_USERNAME)" \
		ADMIN_PASSWORD="$(ADMIN_PASSWORD)" $(PY) -m mykb.db.bootstrap

backend:
	DATABASE_URL="$(DATABASE_URL)" JWT_SECRET="$(JWT_SECRET)" \
		MYKB_SECRET_KEY="$(MYKB_SECRET_KEY)" MYKB_KB_ROOT="$(MYKB_KB_ROOT)" \
		MYKB_WEKNORA_URL="$(MYKB_WEKNORA_URL)" MYKB_WEKNORA_KEY="$(MYKB_WEKNORA_KEY)" \
		MYKB_WEKNORA_TENANT_ID="$(MYKB_WEKNORA_TENANT_ID)" \
		MYKB_WEKNORA_EMBEDDING_MODEL_ID="$(MYKB_WEKNORA_EMBEDDING_MODEL_ID)" \
		MYKB_LLM_BASE_URL="$(MYKB_LLM_BASE_URL)" MYKB_LLM_API_KEY="$(MYKB_LLM_API_KEY)" \
		MYKB_LLM_MODEL="$(MYKB_LLM_MODEL)" \
		$(PY) -m uvicorn mykb.api.app:app --reload --reload-dir mykb \
		--host 127.0.0.1 --port $${BACKEND_PORT:-8000}

frontend:
	cd frontend && npm run dev -- --port $${FRONTEND_PORT:-5173}

dev:
	DATABASE_URL="$(DATABASE_URL)" JWT_SECRET="$(JWT_SECRET)" \
		MYKB_SECRET_KEY="$(MYKB_SECRET_KEY)" MYKB_KB_ROOT="$(MYKB_KB_ROOT)" \
		MYKB_WEKNORA_URL="$(MYKB_WEKNORA_URL)" MYKB_WEKNORA_KEY="$(MYKB_WEKNORA_KEY)" \
		MYKB_WEKNORA_TENANT_ID="$(MYKB_WEKNORA_TENANT_ID)" \
		MYKB_WEKNORA_EMBEDDING_MODEL_ID="$(MYKB_WEKNORA_EMBEDDING_MODEL_ID)" \
		MYKB_LLM_BASE_URL="$(MYKB_LLM_BASE_URL)" MYKB_LLM_API_KEY="$(MYKB_LLM_API_KEY)" \
		MYKB_LLM_MODEL="$(MYKB_LLM_MODEL)" \
		BACKEND_PORT=$${BACKEND_PORT:-8000} FRONTEND_PORT=$${FRONTEND_PORT:-5173} \
		bash scripts/dev.sh

seed:
	$(PY) scripts/seed_demo.py $(BUNDLE)

test:
	$(PY) -m pytest tests/ -q

frontend-test:
	cd frontend && npm test

typecheck:
	$(PY) -m mypy mykb

lint:
	$(PY) -m ruff check mykb tests

check: lint typecheck test

build:
	cd frontend && npm run build

stop:
	-pkill -f "uvicorn mykb.api.app:app"
	-pkill -f "vite"

clean:
	rm -rf .venv frontend/node_modules frontend/dist .npm-cache
