# SkillHub Backend

FastAPI backend for SkillHub, ported from the original Java Spring Boot service.

## Status

The Python backend includes the core API surface for health checks, local auth, API tokens, password reset, RBAC, bootstrap admin, skill publishing, storage, governance, search, social actions, notifications, SSE, admin workflows, scanner integration, schedulers, and deployment assets. The browser-facing `/api/web` contract is backed by real handlers or compatibility aliases to the migrated `/api/v1` handlers.

## Stack

- `uv` for Python environments and dependency locking
- FastAPI with Uvicorn/Gunicorn
- SQLAlchemy 2 async engine with Alembic migrations
- PostgreSQL 16, Redis 7, and MinIO/S3-compatible storage
- Pydantic v2 and pydantic-settings
- Authlib for OAuth2 provider wiring
- APScheduler for maintenance jobs
- `sse-starlette` for notification streams
- Prometheus FastAPI instrumentation at `/metrics`

## Layout

```text
backend/
  src/skillhub_api/      application package
  alembic/               database migrations
  tests/unit/            fast unit tests
  tests/integration/     Postgres-backed integration tests
  scripts/               OpenAPI export, schema diff, maintenance scripts
  openapi/               generated OpenAPI artifacts
  pyproject.toml         project metadata and tool configuration
  uv.lock                locked dependency graph
```

## Local Development

Use `backend/docker-compose.yml` for local Postgres, Redis, and MinIO:

```powershell
docker compose up -d postgres redis minio
if (!(Test-Path .env)) { Copy-Item .env.example .env }
uv sync
uv run alembic upgrade head
uv run uvicorn skillhub_api.main:app --host 0.0.0.0 --port 8080 --reload
```

The default `.env.example` expects Postgres on `127.0.0.1:5432`, Redis on `127.0.0.1:6379`, and MinIO on `127.0.0.1:9000`.

Health checks:

- `http://127.0.0.1:8080/healthz`
- `http://127.0.0.1:8080/api/v1/health`
- `http://127.0.0.1:8080/v3/api-docs`

## Useful Commands

```powershell
uv run pytest tests/unit -q
uv run pytest tests/integration -q -m integration
uv run alembic upgrade head
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run python scripts/export_openapi.py openapi/python-current.json
```

Search rebuild is exposed through `POST /api/v1/admin/search/rebuild` for `SUPER_ADMIN` users and returns `{ rebuilt }` inside the standard API envelope.

The `Makefile` exposes the same operations for Unix-like shells.

## Local Admin

When `BOOTSTRAP_ADMIN_ENABLED=true`, startup creates or updates the configured local admin account:

- Username: `admin`
- Password: `ChangeMe!2026`

Change these values before using a shared or hosted environment.
