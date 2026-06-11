# Byte4Bite — development shortcuts
#
# Install GNU Make on Windows:  winget install GnuWin32.Make
# Alternative without Make:      .\dev.ps1 up
#
# Quick start:
#   make setup    # first-time: env files + dependencies
#   make up       # backend (:8000) + frontend (:3000)
#   make help     # list all targets

.DEFAULT_GOAL := help

ifeq ($(OS),Windows_NT)
SHELL := $(COMSPEC)
.SHELLFLAGS := /c
endif

BACKEND_DIR  := Backend
FRONTEND_DIR := Frontend
PYTHON       ?= python
NPM          ?= npm
PIP          ?= pip
HOST         := 127.0.0.1
BACKEND_PORT := 8000
FRONTEND_PORT := 3000

.PHONY: help setup setup-env install install-backend install-frontend \
        up backend frontend down build build-frontend lint lint-frontend \
        verify backfill ingest migrate db-check health

help:
	@echo Byte4Bite Makefile
	@echo   make setup          First-time env files + pip/npm install
	@echo   make up             Start backend and frontend together
	@echo   make backend        FastAPI only on port $(BACKEND_PORT)
	@echo   make frontend       Next.js only on port $(FRONTEND_PORT)
	@echo   make down           Stop processes on ports $(BACKEND_PORT)/$(FRONTEND_PORT)
	@echo   make verify         Semantic search health check
	@echo   make backfill       Backfill recipe embeddings
	@echo   make ingest         Sync CSV datasets into MySQL
	@echo   make migrate        Apply search_history migration
	@echo   make db-check       Test MySQL connection
	@echo   make health         db-check + verify
	@echo   make build          Production frontend build
	@echo   make lint           Run frontend eslint

setup: setup-env install
	@echo Setup complete. Edit Backend/.env then run: make up

ifeq ($(OS),Windows_NT)
setup-env:
	@if not exist "$(BACKEND_DIR)\.env" (copy "$(BACKEND_DIR)\.env.example" "$(BACKEND_DIR)\.env" && echo Created Backend/.env - set GEMINI_API_KEY and MySQL credentials) else (echo Backend/.env already exists)
	@if not exist "$(FRONTEND_DIR)\.env.local" (echo NEXT_PUBLIC_API_URL=http://$(HOST):$(BACKEND_PORT)> "$(FRONTEND_DIR)\.env.local" && echo Created Frontend/.env.local) else (echo Frontend/.env.local already exists)
else
setup-env:
	@if [ ! -f $(BACKEND_DIR)/.env ]; then \
		cp $(BACKEND_DIR)/.env.example $(BACKEND_DIR)/.env; \
		echo "Created $(BACKEND_DIR)/.env - set GEMINI_API_KEY and MySQL credentials"; \
	else \
		echo "$(BACKEND_DIR)/.env already exists"; \
	fi
	@if [ ! -f $(FRONTEND_DIR)/.env.local ]; then \
		printf 'NEXT_PUBLIC_API_URL=http://%s:%s\n' $(HOST) $(BACKEND_PORT) > $(FRONTEND_DIR)/.env.local; \
		echo "Created $(FRONTEND_DIR)/.env.local"; \
	else \
		echo "$(FRONTEND_DIR)/.env.local already exists"; \
	fi
endif

install: install-backend install-frontend

install-backend:
	cd $(BACKEND_DIR) && $(PIP) install -r requirements.txt

install-frontend:
	cd $(FRONTEND_DIR) && $(NPM) install

up:
	@echo Starting Byte4Bite - backend http://$(HOST):$(BACKEND_PORT) frontend http://$(HOST):$(FRONTEND_PORT)
	@$(MAKE) -j2 backend frontend

backend:
	cd $(BACKEND_DIR) && $(PYTHON) -m uvicorn main:app --host $(HOST) --port $(BACKEND_PORT) --reload

frontend:
	cd $(FRONTEND_DIR) && $(NPM) run dev

down:
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -Command "$$ports = @($(BACKEND_PORT), $(FRONTEND_PORT)); foreach ($$p in $$ports) { Get-NetTCPConnection -LocalPort $$p -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $$_.OwningProcess -Force -ErrorAction SilentlyContinue } }; Write-Host 'Stopped listeners on ports $(BACKEND_PORT) and $(FRONTEND_PORT) (if any)'"
else
	@for port in $(BACKEND_PORT) $(FRONTEND_PORT); do \
		pid=$$(lsof -ti:$$port 2>/dev/null); \
		[ -n "$$pid" ] && kill $$pid 2>/dev/null && echo "Stopped port $$pid" || true; \
	done
	@echo Done.
endif

build: build-frontend

build-frontend:
	cd $(FRONTEND_DIR) && $(NPM) run build

lint: lint-frontend

lint-frontend:
	cd $(FRONTEND_DIR) && $(NPM) run lint

verify:
	cd $(BACKEND_DIR) && $(PYTHON) scripts/verify_semantic_search.py

backfill:
	cd $(BACKEND_DIR) && $(PYTHON) -m rag.backfill_embeddings

ingest:
	cd $(BACKEND_DIR) && $(PYTHON) -m rag.ingest

migrate:
	cd $(BACKEND_DIR) && $(PYTHON) -m scripts.apply_migration_002

db-check:
	cd $(BACKEND_DIR) && $(PYTHON) -c "from database.connection import ping_database; print('MySQL OK' if ping_database() else 'MySQL FAILED')"

health: db-check verify
