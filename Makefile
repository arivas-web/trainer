# Pulse · tareas habituales. `make help` para la lista.
SHELL := /bin/bash
BACKEND := cd backend &&
FRONTEND := cd frontend &&
PY := uv run

.PHONY: help setup db-up db-down migrate dev sync summary probe token-check import \
        test lint format requirements schema-sql key

help: ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Instala dependencias (uv + npm) y crea .env.local si no existe
	$(BACKEND) uv sync
	$(FRONTEND) npm ci
	@test -f .env.local || (cp .env.example .env.local && echo "Creado .env.local: rellénalo")

db-up: ## Postgres local en Docker (puerto 5432)
	docker run -d --name pulse-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=pulse \
	  -p 5432:5432 -v pulse-pg:/var/lib/postgresql/data postgres:16

db-down: ## Para el Postgres local
	docker rm -f pulse-pg

migrate: ## Aplica las migraciones a DATABASE_URL
	$(BACKEND) $(PY) python -m app.cli migrate

dev: ## Backend (8000) + frontend (5173) con recarga en caliente
	@trap 'kill 0' EXIT; \
	($(BACKEND) $(PY) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) & \
	($(FRONTEND) npm run dev) & wait

sync: ## Sincroniza con Garmin y muestra el resumen
	$(BACKEND) $(PY) python -m app.cli sync

summary: ## Resumen de lo descargado
	$(BACKEND) $(PY) python -m app.cli summary

probe: ## Lista y prueba los endpoints del OpenAPI de Garmin (formas, sin valores)
	$(BACKEND) $(PY) python -m app.cli probe --call

token-check: ## Comprueba la clave API personal de Garmin
	$(BACKEND) $(PY) python -m app.cli token-check

import: ## Importa archivos: make import FILES="ruta/al/export.zip"
	$(BACKEND) $(PY) python -m app.cli import $(abspath $(FILES))

test: ## Tests de backend y build de frontend
	$(BACKEND) $(PY) pytest
	$(FRONTEND) npm run build

lint: ## ruff + mypy + eslint + prettier + tsc, y requirements.txt al día
	$(BACKEND) $(PY) ruff check . && $(PY) ruff format --check . && $(PY) mypy app
	$(FRONTEND) npm run lint && npm run typecheck
	@$(BACKEND) uv export --no-dev --no-hashes --no-emit-project --quiet -o ../requirements.txt.check \
	  && cd .. && (diff -q <(grep -v '^#' requirements.txt) <(grep -v '^#' requirements.txt.check) >/dev/null \
	  || (echo "requirements.txt desactualizado: make requirements"; rm requirements.txt.check; exit 1)) \
	  && rm requirements.txt.check

format: ## Formatea backend y frontend
	$(BACKEND) $(PY) ruff format . && $(PY) ruff check --fix .
	$(FRONTEND) npm run format

requirements: ## Regenera requirements.txt (lo usa Vercel) desde backend/uv.lock
	$(BACKEND) uv export --no-dev --no-hashes --no-emit-project --quiet -o ../requirements.txt

schema-sql: ## Regenera supabase/01_schema.sql (esquema para pegar en Supabase)
	@{ echo "-- Pulse · esquema completo (GENERADO con \`make schema-sql\`; no editar a mano)."; \
	  echo "-- Pégalo entero en Supabase → SQL Editor → Run. Equivale a \`make migrate\`."; echo; \
	  cd backend && DATABASE_URL=postgresql+psycopg://x@localhost/x $(PY) alembic upgrade head --sql 2>/dev/null; } > supabase/01_schema.sql

key: ## Genera una clave aleatoria (TOKEN_ENCRYPTION_KEY / CRON_SECRET)
	@$(BACKEND) $(PY) python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
