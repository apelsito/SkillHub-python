# SkillHub

SkillHub is a self-hosted skill registry for AI agent teams. This workspace contains the FastAPI backend and the React/Vite frontend that were ported from the original Java Spring Boot implementation.

## Repository Layout

```text
skillhub-api/
  backend/   FastAPI service, Alembic migrations, tests, Docker assets
  frontend/  React web client, Vite config, UI tests, static assets
```

## Requirements

- Python 3.12 or newer
- `uv` 0.11 or newer
- Node.js 20 or newer
- `pnpm`
- Docker or Podman with Docker-compatible Compose

## Local Infrastructure

Use the checked-in Compose stack as the official local database strategy:

```powershell
cd C:\Users\ruipe\Desktop\skillhub-api\backend
docker compose up -d postgres redis minio
```

The default `backend/.env.example` expects:

- Postgres: `127.0.0.1:5432`
- Redis: `127.0.0.1:6379`
- MinIO API: `127.0.0.1:9000`
- MinIO console: `127.0.0.1:9001`

If you already have a local `backend/.env`, keep it private and make sure its ports match your running containers.

## Backend

```powershell
cd C:\Users\ruipe\Desktop\skillhub-api\backend
if (!(Test-Path .env)) { Copy-Item .env.example .env }
uv sync
uv run alembic upgrade head
uv run uvicorn skillhub_api.main:app --host 0.0.0.0 --port 8080 --reload
```

Health and API docs:

- `http://127.0.0.1:8080/healthz`
- `http://127.0.0.1:8080/api/v1/health`
- `http://127.0.0.1:8080/v3/api-docs`

To enable the local bootstrap admin, set `BOOTSTRAP_ADMIN_ENABLED=true` in `backend/.env` before starting the backend. The example credentials are:

- Username: `admin`
- Password: `ChangeMe!2026`

Change these values before using a shared environment.

## Frontend

```powershell
cd C:\Users\ruipe\Desktop\skillhub-api\frontend
pnpm install
pnpm dev
```

The frontend runs on `http://127.0.0.1:3000` and proxies API calls to `http://127.0.0.1:8080`.

## Search Rebuild

The local Postgres database owns the `skill_search_document` table and indexes via Alembic. After publishing sample skills or migrating data, rebuild the search index with an admin session:

```powershell
cd C:\Users\ruipe\Desktop\skillhub-api\backend
uv run alembic upgrade head
```

Then call the admin endpoint from the running app:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/v1/admin/search/rebuild -WebSession $session
```

The response data contains `rebuilt`, the number of search documents written.

## Verification

Backend:

```powershell
cd C:\Users\ruipe\Desktop\skillhub-api\backend
uv run pytest tests/unit -q
uv run pytest tests/integration -q
```

Frontend:

```powershell
cd C:\Users\ruipe\Desktop\skillhub-api\frontend
pnpm test -- --run
pnpm build
```

## Development Notes

- Use `/api/web/*` as the browser-facing contract.
- Keep `/api/v1/*` routes working for compatibility and CLI usage.
- Keep user-facing UI, docs, and validation messages in English.
- Do not commit local `.env`, `.venv`, `node_modules`, build output, or Python cache files.
