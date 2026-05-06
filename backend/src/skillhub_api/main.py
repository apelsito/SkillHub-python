"""FastAPI app factory.

Phase 0-4 surface: health, auth, skills core, governance (reviews, reports,
profile-change, audit read, promotions). Post-commit event bus is
wired as middleware so services can enqueue events during a request and
they dispatch to registered listeners once the response is produced.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.sessions import SessionMiddleware

from skillhub_api import __version__
from skillhub_api.api_envelope import ApiEnvelopeMiddleware
from skillhub_api.errors import register_exception_handlers
from skillhub_api.events.bus import get_event_bus
from skillhub_api.events.listeners import (
    register_audit_listeners,
    register_notification_listeners,
    register_search_listeners,
    register_social_listeners,
)
from skillhub_api.events.middleware import EventDispatchMiddleware
from skillhub_api.infra.db.session import AsyncSessionLocal, dispose_engine
from skillhub_api.infra.redis_client import close_redis
from skillhub_api.infra.stream import get_stream_consumer
from skillhub_api.logging import configure_logging, get_logger
from skillhub_api.routers.admin import router as admin_router
from skillhub_api.routers.auth import router as auth_router
from skillhub_api.routers.compat import router as compat_router
from skillhub_api.routers.health import router as health_router
from skillhub_api.routers.portal import router as portal_router
from skillhub_api.scheduling import get_scheduler
from skillhub_api.services.auth.bootstrap import ensure_bootstrap_admin
from skillhub_api.settings import get_settings
from skillhub_api.sse.manager import get_stream_manager

logger = get_logger(__name__)


_WEB_ALIAS_PREFIXES = (
    ("/api/v1/skills", "/api/web/skills"),
    ("/api/v1/labels", "/api/web/labels"),
    ("/api/v1/notifications", "/api/web/notifications"),
    ("/api/v1/reviews", "/api/web/reviews"),
    ("/api/v1/promotions", "/api/web/promotions"),
    ("/api/v1/namespaces", "/api/web/namespaces"),
    ("/api/v1/me", "/api/web/me"),
    ("/api/web/governance", "/api/v1/governance"),
)


def _install_web_aliases(app: FastAPI) -> None:
    """Expose Java-compatible /api/web aliases for migrated /api/v1 handlers."""

    def _java_param_names(path: str) -> str:
        return (
            path.replace("{skill_id}", "{skillId}")
            .replace("{user_id}", "{userId}")
            .replace("{tag_name}", "{tagName}")
            .replace("{label_slug}", "{labelSlug}")
        )

    existing_routes = {
        (getattr(route, "path", ""), method)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    for route in list(app.routes):
        if not isinstance(route, APIRoute):
            continue
        for source_prefix, target_prefix in _WEB_ALIAS_PREFIXES:
            if route.path != source_prefix and not route.path.startswith(f"{source_prefix}/"):
                continue
            alias_path = _java_param_names(f"{target_prefix}{route.path[len(source_prefix):]}")
            if all((alias_path, method) in existing_routes for method in route.methods):
                continue
            app.add_api_route(
                alias_path,
                route.endpoint,
                response_model=route.response_model,
                status_code=route.status_code,
                tags=route.tags,
                dependencies=route.dependencies,
                summary=route.summary,
                description=route.description,
                response_description=route.response_description,
                responses=route.responses,
                deprecated=route.deprecated,
                methods=route.methods,
                operation_id=None,
                response_class=route.response_class,
                name=f"{route.name}_web_alias",
                openapi_extra=route.openapi_extra,
            )
            for method in route.methods:
                existing_routes.add((alias_path, method))
            break


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "skillhub.startup",
        app=settings.app_name,
        version=__version__,
        port=settings.server_port,
    )

    if settings.bootstrap_admin.enabled:
        try:
            async with AsyncSessionLocal()() as session:
                await ensure_bootstrap_admin(session)
        except Exception as exc:  # pragma: no cover - surfaced at runtime only
            logger.error("bootstrap.admin_failed", error=str(exc))

    stream_manager = get_stream_manager()
    await stream_manager.start_redis_bridge()

    # Scan-task stream consumer — best-effort; if Redis or the scanner
    # are unavailable in dev the consumer logs a warning and stays idle.
    scan_consumer = get_stream_consumer()
    await scan_consumer.start()

    # Periodic maintenance jobs. APScheduler runs them on this process's
    # event loop; the Redis single-instance lock guards against
    # duplicate execution when multiple replicas are deployed.
    scheduler = get_scheduler()
    scheduler.start()

    try:
        yield
    finally:
        await scheduler.shutdown()
        await scan_consumer.shutdown()
        await stream_manager.stop_redis_bridge()
        await close_redis()
        await dispose_engine()
        logger.info("skillhub.shutdown")


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="SkillHub API",
        version=__version__,
        description=(
            "Python port of the SkillHub Spring Boot backend. The OpenAPI surface "
            "is contract-compatible with the Java service so the React frontend "
            "consumes it unchanged."
        ),
        lifespan=_lifespan,
        docs_url="/swagger-ui",
        redoc_url="/redoc",
        openapi_url="/v3/api-docs",
    )

    # Event bus: register listeners once per process, then wrap every
    # request in a buffer context so services can enqueue events.
    bus = get_event_bus()
    register_audit_listeners(bus)
    register_search_listeners(bus)
    register_social_listeners(bus)
    register_notification_listeners(bus)
    app.add_middleware(EventDispatchMiddleware)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.download_anon_cookie_secret.get_secret_value(),
        session_cookie="SKILLHUB_SESSION",
        max_age=int(settings.session_timeout.total_seconds()),
        https_only=settings.session_cookie_secure,
        same_site="lax",
    )

    register_exception_handlers(app)

    # Envelope wrapping happens outermost, *after* exception handlers have
    # formatted an error body — otherwise the envelope runs on raw
    # exceptions. We install it last so it sits at the top of the stack.
    app.add_middleware(ApiEnvelopeMiddleware)

    # Metrics — expose at /metrics (Prometheus scrape path).
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(portal_router)
    app.include_router(admin_router)
    app.include_router(compat_router)
    _install_web_aliases(app)

    return app


app = create_app()
