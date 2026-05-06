# SkillHub API — Handoff

This file tracks what was built in the initial landing and what still needs to happen for the Java → Python rewrite to reach parity with the existing Spring Boot backend.

The approved plan lives at `C:\Users\ruipe\.claude\plans\genera-skillhub-en-python-synthetic-wolf.md`.

## Status matrix

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Scaffolding (pyproject, Dockerfile, compose, CI, base app, healthcheck, structlog, metrics) | **Done** |
| 1a | Settings mirroring `application.yml`, async DB engine, session factory | **Done** |
| 1b | SQLAlchemy 2 ORM models for all 35 tables grouped by aggregate | **Done** |
| 1c | Alembic baseline (`alembic/versions/20260506_0001_initial_schema_v40.py`) that brings an empty DB to a V40-equivalent schema | **Done** |
| 1d | Integration harness using `testcontainers-postgres` + schema assertions | **Done** |
| 2 | Auth stack (local, OAuth2, tokens, device, merge, RBAC, sessions, bootstrap admin) | **Partial** — see below |
| 2a | Local auth (register/login/logout/change-password) with 5-strike 15-min lockout | **Done** |
| 2b | API tokens (`sk_` + base64url, SHA-256 hash, bearer auth resolver) | **Done** |
| 2c | Password reset flow (6-digit numeric code, bcrypt hash, PT10M expiry) | **Done** |
| 2d | RBAC permission dep + SUPER_ADMIN wildcard | **Done** |
| 2e | Bootstrap admin on startup (flag-gated) | **Done** |
| 2f | Session middleware (Starlette + cookie) | **Done** |
| 2g | OAuth2 GitHub/GitLab (authlib + state in Redis + identity_binding upsert) | **Skeleton** — returns 501 |
| 2h | Device authorization flow | **Not started** |
| 2i | Account merge (initiate → verify → confirm) | **Not started** |
| 2j | Mock/direct auth modes | **Not started** |
| 3 | Skills core (publish, CRUD, storage, idempotency, rate limits) | **Partial** — see below |
| 3a | Storage abstraction + LocalFileStorage + S3Storage (aioboto3) | **Done** |
| 3b | Package policy (48 allowed extensions, size limits, path traversal guard, zip extract) | **Done** |
| 3c | Manifest parser (YAML frontmatter in SKILL.md) | **Done** |
| 3d | Publish flow (PRIVATE → PUBLISHED, PUBLIC/NAMESPACE_ONLY → PENDING_REVIEW) | **Done** |
| 3e | List/get skill, list versions, list files, get version detail | **Done** |
| 3f | Download (local stream + S3 presigned URL redirect) + counter increment | **Done** |
| 3g | Lifecycle actions (archive, unarchive, yank version) — owner-only | **Done** |
| 3h | Deterministic bundle.zip build | **Done** |
| 3i | Idempotency repository (X-Request-Id) | **Done** — middleware wiring pending |
| 3j | Rate limiting on download + anon cookie | **Not started** |
| 3k | Admin-override for lifecycle actions | **Not started** (Phase 7) |
| 4 | Governance + event bus (reviews, promotions, reports, audit, profile change) | **Partial** — see below |
| 4a | Post-commit event bus (asyncio.TaskGroup + ContextVar buffer + middleware) | **Done** |
| 4b | 18 domain events as dataclasses | **Done** |
| 4c | Review workflow (submit by owner, approve/reject by reviewer, version status flip) | **Done** |
| 4d | Skill reports (user submit + admin list/handle + HIDDEN/REMOVED side-effects) | **Done** |
| 4e | Audit log read API with filters (audit:read permission) | **Done** |
| 4f | Profile change workflow (submit, approve, reject, editable fields allowlist) | **Done** |
| 4g | Audit listener — auto-writes audit_log row on every governance event | **Done** |
| 4h | `SkillPublishedEvent` wired on private publish | **Done** |
| 4i | Promotions skeleton (list pending + 501 on approve/reject) | **Done** |
| 4j | Promotion approve/reject full flow (target-skill conflict resolution, version copy) | **Not started** |
| 4k | Review re-submit after rejection | **Not started** |
| 5 | Search (jieba, hashed embedding, tsvector query builder) | **Partial** — see below |
| 5a | Java ``String.hashCode()`` port (UTF-16 code units + 32-bit wraparound) | **Done** |
| 5b | Tokenizer (``jieba.cut_for_search`` for index, ``cut(HMM=True)`` for query) | **Done** |
| 5c | 64-dim hashed embedding with 0.35 trigram weight + L2 + `%.6f` serialization | **Done** |
| 5d | Document builder (title/summary/keywords/search_text/semantic_vector) | **Done** |
| 5e | Search index service (UPSERT by skill_id, remove on archive) | **Done** |
| 5f | Full-text query with tsquery + prefix + 4 sort orders + semantic blending | **Done** |
| 5g | Listener wiring: SkillPublished/StatusChanged/Yanked → reindex/remove | **Done** |
| 5h | REST endpoint ``/api/v1/skills/search`` | **Done** |
| 5i | Rebuild script ``scripts/rebuild_search_index.py`` | **Done** |
| 5j | Golden-file tokenizer tests vs Java jieba-analysis reference output | **Not started** (risk: jieba drift) |
| 5k | Namespace-scoped visibility (NAMESPACE_ONLY + member check) | **Not started** (Phase 7 RBAC) |
| 6 | Social + notifications + SSE | **Partial** — see below |
| 6a | Star / unstar endpoints + has_starred check, rollup to `skill.star_count` | **Done** |
| 6b | Rating upsert (1-5), `skill.rating_avg` / `rating_count` rollup | **Done** |
| 6c | Subscribe / unsubscribe endpoints + inline `subscription_count` update | **Done** |
| 6d | Notification list / unread-count / mark-read / mark-all-read / delete | **Done** |
| 6e | Notification preferences (GET with defaults + PUT bulk upsert) | **Done** |
| 6f | Notification fan-out listener — 11 event→notification mappings | **Done** |
| 6g | SSE endpoint ``/api/v1/notifications/sse`` with per-user asyncio queue | **Done** |
| 6h | Redis pub/sub bridge for cross-pod SSE delivery | **Done** |
| 6i | Connection limits (5/user, 1000/process, 10-min timeout, 30-sec heartbeat) | **Done** |
| 6j | Email / Feishu / DingTalk channels | **Not started** (Java only has IN_APP today) |
| 7 | Admin + labels + scanner HTTP client + ClawHub compat | **Partial** — see below |
| 7a | `require_any_role()` dep (RBAC via role codes with SUPER_ADMIN wildcard) | **Done** |
| 7b | Admin skill moderation (`hide`/`unhide`/`yank`) | **Done** |
| 7c | User management (list/search + role/status/approve/disable/enable/password-reset) | **Done** |
| 7d | Admin profile-review list endpoint | **Done** |
| 7e | Label admin CRUD (create/update/delete/sort-order + translations) with limits | **Done** |
| 7f | Public label list + per-skill attach/detach (owner-only) | **Done** |
| 7g | Skill tag CRUD (named pointers to versions) | **Done** |
| 7h | Admin search `/rebuild` endpoint | **Done** |
| 7i | Scanner HTTP client (local + upload modes, retry/backoff, respx-tested) | **Done** |
| 7j | ClawHub compat core (search / skills list / skill detail / download redirect / whoami) | **Done** |
| 7k | ClawHub compat skeletons (resolve, stars, publish) | **Skeleton** — return 501 |
| 7l | `/.well-known/clawhub.json` | **Done** |
| 7m | Scanner wire-up in publish flow | **Not started** (currently bypassed) |
| 7n | Namespace-member RBAC for label/tag bindings | **Not started** (owner-only today) |
| 7o | Audit entries for admin mutations | **Not started** (listener gap) |
| 8 | Schedulers + Redis Streams consumer + deploy compose + observability | **Partial** — see below |
| 8a | APScheduler with 4 maintenance jobs (idempotency, notification, compensation) | **Done** |
| 8b | Redis single-instance lock for scheduled jobs (`SET NX EX`) | **Done** |
| 8c | Redis Streams scan-task consumer (XREADGROUP + XAUTOCLAIM reclaim) | **Done** |
| 8d | Scan-task producer (`enqueue_scan_task`) | **Done** |
| 8e | `security_audit` row written per scan result | **Done** |
| 8f | `SensitiveLogSanitizer` — scrubs password / token / api_key / etc from log events | **Done** |
| 8g | `compose.release.yml` + `.env.release.example` + `docker-compose.staging.yml` | **Done** |
| 8h | Graceful shutdown: scheduler → stream consumer → SSE bridge → Redis → DB | **Done** |
| 8i | Prometheus `/metrics` exposed (was already in Phase 0) | **Done** |
| 8j | Stream byte-streaming from storage instead of empty payload stub | **Not started** (current consumer submits empty body) |
| 8k | k6 / locust load test suite | **Not started** |

## What was delivered (Phases 0 + 1)

- **FastAPI app factory** at `src/skillhub_api/main.py` — boots with structlog JSON logging, registers exception handlers, mounts Prometheus metrics at `/metrics`, exposes OpenAPI at `/v3/api-docs` (same path Spring uses so `openapi-typescript` keeps working).
- **Health endpoints** at `/healthz`, `/actuator/health`, `/api/v1/health`.
- **Settings** (`src/skillhub_api/settings.py`) — every env var name matches the Java service exactly, so existing secret stores and compose files can be reused.
- **Error contract** (`src/skillhub_api/errors.py`) — `DomainError`/`NotFoundError`/`ConflictError`/`ForbiddenError`/`UnauthorizedError` + handlers producing `{code, message, details}` JSON bodies matching Spring's `@ControllerAdvice` output.
- **ORM models** — 35 tables across 12 domain modules under `src/skillhub_api/infra/db/models/`, all TIMESTAMPTZ, JSONB where the Java uses it, partial unique indexes for `PENDING` workflow rows, and the `search_vector` STORED generated column wired through `Computed(..., persisted=True)`.
- **Alembic baseline** — single revision containing every table, every index (including partial and GIN), all CHECK constraints, and the seed data (4 system roles, 8 permissions, role-permission bindings, `global` namespace).
- **Integration test harness** — `tests/integration/conftest.py` spins up Postgres 16 via testcontainers, runs Alembic, and hands out transaction-scoped `AsyncSession` fixtures. `tests/integration/test_schema.py` asserts the full table set, seed data, STORED generated column, and CHECK constraint behavior.
- **Unit tests** — 16 passing tests covering health, settings parser, and error handlers.
- **CI** — GitHub Actions workflow running lint, typecheck, unit tests, OpenAPI export, and schema-diff against the Java baseline.
- **Docker compose** — Postgres 16 + Redis 7 + MinIO + api, env-var-parity with the Java deployment.
- **Schema diff gate** (`scripts/schema_diff.py`) — compares `openapi/java-baseline.json` vs `openapi/python-current.json` using `deepdiff`, fails CI on contract-breaking changes (removed path/field, type change) while allowing additive changes.

## How to continue

### Local setup

Dependency management: **uv** (`pyproject.toml` + `uv.lock`). uv creates and owns `.venv/`; you don't need to `python -m venv`.

```bash
cd skillhub-api
uv sync                                    # creates .venv from uv.lock, installs project + dev group
uv run pytest tests/unit -q                # 16 pass
uv run alembic upgrade head --sql | head   # compiles the baseline without a live DB
```

Integration tests need Docker:
```bash
uv run pytest tests/integration -q -m integration
```

Adding deps: `uv add <pkg>` for runtime, `uv add --group dev <pkg>` for dev-only. CI uses `uv sync --frozen` so the lockfile is authoritative.

### First tasks for Phase 2 (auth stack)

Map Java classes to Python modules. Start here:

- [server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/config/SecurityConfig.java](../server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/config/SecurityConfig.java) → `src/skillhub_api/deps.py` + middleware in `src/skillhub_api/main.py`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/local/` → `src/skillhub_api/routers/auth/local.py` + `src/skillhub_api/services/auth/local.py`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/oauth/` → `src/skillhub_api/routers/auth/oauth.py` using `authlib`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/` → `src/skillhub_api/routers/auth/tokens.py`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/device/` → `src/skillhub_api/routers/auth/device.py`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/merge/` → `src/skillhub_api/routers/auth/merge.py`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/rbac/` → `src/skillhub_api/services/auth/rbac.py` + permission-check dep in `deps.py`

Each Java `@RestController` method becomes a FastAPI route. Each `@Service` method becomes a function under `services/`. Repository adapters go under `infra/repositories/`.

### What to verify as each phase lands

1. `make test-unit` stays green (mock DB; fast).
2. `make test-integration` stays green (real Postgres, testcontainers).
3. `make openapi` exports the current schema.
4. CI schema-diff stays green (or the baseline is updated with a rationale comment).
5. Frontend smoke: `pnpm dev` inside `web/`, pointed at the Python backend, exercising the 10 canonical flows listed in the plan §9.

### Known shortcuts / TODOs

- **Host addresses: always IPv4 (`127.0.0.1`), never `localhost`.** On Windows `localhost` resolves to `::1` first; asyncpg, uvicorn, Vite proxies all fail with `ConnectionRefusedError [WinError 1225]` before falling back to IPv4. Every env var, default, doc link, and dev-server proxy must use `127.0.0.1` explicitly. Healthchecks *inside* Docker containers may use `localhost` (they hit the container's own loopback on Linux, no IPv6 issue).
- **Password hashing algorithm**: not yet chosen. Confirm bcrypt cost factor from the Spring `PasswordEncoder` bean before implementing `passlib[bcrypt]` so credentials round-trip during any overlap.
- **Alembic baseline is hand-written**. Future schema changes should use `alembic revision --autogenerate` but the autogenerate output should be reviewed for Postgres-specific pieces (generated columns, partial indexes) that autogenerate often misses — this is why the initial revision was written by hand.
- **Seed data is English**. The Python baseline keeps system role and permission names in English.
- **`openapi/java-baseline.json` is missing**. The CI schema-diff step is marked `continue-on-error: true` until the baseline is committed. Generate it with: start the Java service locally → `curl http://127.0.0.1:8080/v3/api-docs > openapi/java-baseline.json` → commit → flip the CI flag to `false`.
- **ClawHub compat controller** has 14 endpoints that need byte-for-byte URL and response parity to keep older CLIs working. Treat as late-phase work with heavy fixture-based tests.
- **Redis Streams consumer** (`ScanTaskConsumer`) must implement `XAUTOCLAIM` reclaim; don't skip it — the Java version relies on reclaim for consumer-death recovery.
- **SSE cross-pod fan-out** (Phase 6) must use Redis pub/sub — in-process emitters only work single-pod and will silently break multi-pod deploys.

## Repository layout quick reference

```
skillhub-api/
├── HANDOFF.md                     (this file)
├── README.md                      quick-start + make targets
├── pyproject.toml                 deps + tool config (uv-managed)
├── uv.lock                        pinned versions; CI installs with --frozen
├── Dockerfile                     multi-stage, gunicorn+uvicorn
├── docker-compose.yml             pg 16, redis, minio, api
├── Makefile                       install / lint / test / run / db / openapi
├── .env.example                   every Java env var mirrored
├── .github/workflows/ci.yml       lint + typecheck + tests + schema-diff
├── alembic.ini
├── alembic/
│   ├── env.py                     async engine wiring
│   └── versions/20260506_0001_initial_schema_v40.py
├── scripts/
│   ├── export_openapi.py
│   └── schema_diff.py
├── tests/
│   ├── conftest.py                TestClient fixture
│   ├── unit/                      16 tests passing
│   └── integration/               testcontainers harness + schema assertions
├── openapi/
│   └── java-baseline.json         (TODO — commit snapshot from Spring)
└── src/skillhub_api/
    ├── __init__.py
    ├── main.py                    FastAPI factory, health, metrics
    ├── settings.py                pydantic-settings mirror of application.yml
    ├── logging.py                 structlog JSON
    ├── errors.py                  DomainError hierarchy + handlers
    ├── routers/
    │   └── health.py              (only one wired so far)
    └── infra/db/
        ├── base.py                DeclarativeBase + naming convention
        ├── session.py             async engine + sessionmaker
        └── models/                12 modules, 35 tables
```
