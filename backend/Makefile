UV ?= uv

.PHONY: install sync lock lint format typecheck test test-unit test-integration run \
        openapi db-upgrade db-revision db-downgrade clean

# `uv sync` installs project + default groups (dev). Use `make sync-prod` for runtime only.
install sync:
	$(UV) sync

sync-prod:
	$(UV) sync --no-dev

lock:
	$(UV) lock

lint:
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

format:
	$(UV) run ruff format src tests

typecheck:
	$(UV) run mypy

test: test-unit

test-unit:
	$(UV) run pytest tests/unit -q

test-integration:
	$(UV) run pytest tests/integration -q -m integration

run:
	$(UV) run uvicorn skillhub_api.main:app --host 0.0.0.0 --port 8080 --reload

openapi:
	$(UV) run python scripts/export_openapi.py openapi/python-current.json

db-upgrade:
	$(UV) run alembic upgrade head

db-revision:
	@test -n "$(m)" || (echo "usage: make db-revision m=\"message\""; exit 1)
	$(UV) run alembic revision --autogenerate -m "$(m)"

db-downgrade:
	$(UV) run alembic downgrade -1

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
