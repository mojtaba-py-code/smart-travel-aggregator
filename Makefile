.PHONY: install dev lint format type test cov run migrate up down clean

VENV ?= .venv
PY := $(VENV)/Scripts/python.exe

install:
	python -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check app tests

format:
	$(PY) -m ruff check app tests --fix
	$(PY) -m black app tests

type:
	$(PY) -m mypy app

test:
	$(PY) -m pytest

cov:
	$(PY) -m pytest --cov-report=html

run:
	$(PY) -m uvicorn app.main:app --reload

migrate:
	$(PY) -m alembic upgrade head

revision:
	$(PY) -m alembic revision --autogenerate -m "$(m)"

up:
	docker compose up --build -d

down:
	docker compose down

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage *.db
