.PHONY: api cli migrate seed db db-down docs

## API HTTP (FastAPI) em http://127.0.0.1:8000
api:
	PYTHONPATH=src uv run uvicorn api:app --host 127.0.0.1 --port 8000 --reload

## CLI com mensagens de exemplo
cli:
	PYTHONPATH=src uv run python src/main.py

## Aplica migrações do banco (alembic upgrade head)
migrate:
	uv run python migrate.py

## Popula o catálogo com peças e tabela de equivalência de exemplo
seed:
	PYTHONPATH=src uv run python scripts/seed.py

## Sobe o Postgres + pgvector (Docker)
db:
	docker compose up -d

## Derruba o Postgres (Docker)
db-down:
	docker compose down

## Abre o Swagger UI no navegador
docs:
	open http://127.0.0.1:8000/docs
