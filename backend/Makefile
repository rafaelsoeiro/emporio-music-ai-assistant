.PHONY: install dev test lint format migrate migration ingest index-policies

install:
	python -m pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload

test:
	pytest

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(message)"

ingest:
	python -m app.scripts.ingest_csv --data-dir app/data

index-policies:
	python -m app.scripts.index_policies

