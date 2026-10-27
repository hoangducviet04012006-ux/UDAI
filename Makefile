# =====================================================================
# BaoHanhAI (KT2 + KT3) - lenh chuan cua du an
# Windows/PowerShell neu may chua co `make` thi dung:  .\dev.ps1 <task>
# =====================================================================

PY       ?= py
PYFLAGS  ?= -3.12
UVICORN  ?= $(PY) $(PYFLAGS) -m uvicorn

BACKEND  := backend
TESTS    := tests
EVIDENCE := docs/evidence

.DEFAULT_GOAL := help
.PHONY: help install install-chat dev initdb resetdb seed evidence test check workflow workbench ui health tree clean up down logs psql

help: ## Hien thi danh sach lenh
	@echo "BaoHanhAI (KT2 + KT3) - lenh phat trien"
	@echo ""
	@echo "  make install   - tao backend/.venv va cai requirements (chay 1 lan)"
	@echo "  make install-chat - cai thu vien AI chatbot (LangChain/LangGraph - tuy chon)"
	@echo "  make initdb    - tao 16 bang trong database/baohanh_ai.db (11 core + 5 chatbot)"
	@echo "  make resetdb   - XOA du lieu demo -> tao lai + nap seed (trang thai sach)"
	@echo "  make seed      - nap du lieu mau"
	@echo "  make dev       - chay API + giao dien web (http://127.0.0.1:8000/docs)"
	@echo "  make evidence  - chay 25 minh chung -> docs/evidence/minh_chung_KT2_KT3.txt"
	@echo "  make test      - chay 25 minh chung (chi in man hinh)"
	@echo "  make workflow  - kiem thu vong doi phieu bao hanh (CASE 1..8)"
	@echo "  make workbench - kiem thu man hinh cong viec theo vai tro (CASE A..H)"
	@echo "  make ui        - smoke test giao dien (Node, khong can trinh duyet)"
	@echo "  make check     - chay minh chung + nghiep vu phieu + man hinh cong viec + giao dien"
	@echo "  make health    - goi /health va /api cua backend dang chay"
	@echo "  make tree      - in cay thu muc"
	@echo "  make clean     - xoa __pycache__ / .pytest_cache"
	@echo "  make up/down/logs/psql - PostgreSQL 16 bang Docker (tuy chon)"

install: ## Tao venv va cai dependencies
	cd $(BACKEND) && $(PY) $(PYFLAGS) -m venv .venv && \
	.venv/Scripts/python -m pip install -U pip && \
	.venv/Scripts/python -m pip install -r requirements.txt || \
	( cd $(BACKEND) && .venv/bin/python -m pip install -U pip && .venv/bin/python -m pip install -r requirements.txt )

dev: ## Chay API (reload)
	cd $(BACKEND) && $(UVICORN) app.main:app --host 127.0.0.1 --port 8000 --reload

install-chat: ## [KT4/P0] Cai thu vien AI cho chatbot (LangChain/LangGraph/FAISS - tuy chon)
	cd $(BACKEND) && $(PY) $(PYFLAGS) -m pip install -r requirements-ai-chat.txt

initdb: ## Khoi tao 16 bang CSDL (11 core KT1 + 5 chatbot KT4)
	$(PY) $(PYFLAGS) $(TESTS)/init_db.py

resetdb: ## Xoa du lieu demo -> tao lai 16 bang -> nap seed (trang thai sach)
	$(PY) $(PYFLAGS) $(TESTS)/init_db.py --reset
	$(PY) $(PYFLAGS) $(TESTS)/seed_data.py

seed: ## Nap du lieu mau
	$(PY) $(PYFLAGS) $(TESTS)/seed_data.py

evidence: ## Chay 25 minh chung, luu log UTF-8 vao docs/evidence/
	$(PY) $(PYFLAGS) $(TESTS)/test_scenarios.py | Out-File -Encoding utf8 $(EVIDENCE)/minh_chung_KT2_KT3.txt

test: ## Chay 25 minh chung (khong luu file)
	$(PY) $(PYFLAGS) $(TESTS)/test_scenarios.py

workflow: ## Kiem thu vong doi phieu bao hanh (CASE 1..8)
	$(PY) $(PYFLAGS) $(TESTS)/test_ticket_workflow.py

workbench: ## Kiem thu man hinh cong viec theo vai tro (CASE A..H)
	$(PY) $(PYFLAGS) $(TESTS)/test_role_workbench.py

ui: ## Smoke test giao dien (Node)
	node $(TESTS)/smoke_frontend.js

check: test workflow workbench ui ## Cong kiem tra truoc khi nop bai

health: ## Kiem tra backend dang chay
	curl -s http://127.0.0.1:8000/health && curl -s http://127.0.0.1:8000/api

tree: ## In cay thu muc (2 cap)
	@echo "backend/  frontend/  database/  docs/  tests/  dev.ps1  Makefile  docker-compose.yml"

clean: ## Xoa cache
	@echo "Don cache __pycache__ / .pytest_cache ..."
	-find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

up: ## Chay PostgreSQL (Docker)
	docker compose up -d db

down: ## Dung container (giu du lieu)
	docker compose down

logs: ## Log cua db
	docker compose logs -f db

psql: ## Mo psql trong container
	docker compose exec db psql -U baohanh -d baohanh_ai
