"""TULYA — FastAPI application factory.

Replaces the prototype's single Flask `api/app.py`. Routers are mounted per
domain; business logic lives in services and repositories, not in handlers.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .logging_setup import configure_logging, get_logger
from .matching.backends import BackendUnavailable, resolve_all

configure_logging()
log = get_logger()

DESCRIPTION = """
Evidence-backed material equivalence across CPSEs.

**AI proposes -> engineering evidence decides -> hard conflicts veto ->
humans govern -> CNMC -> audit + procurement impact.**

The local LLM is used only for structured attribute extraction from free-text
descriptions. It never decides equivalence: that comes from deterministic
attribute comparison, the hard-key veto and a named steward's approval.
"""


def create_app() -> FastAPI:
    # Fail fast and loudly rather than serving with a backend we do not claim.
    try:
        backends = resolve_all()
    except BackendUnavailable as exc:
        log.error("startup.backend_unavailable", error=str(exc))
        raise

    app = FastAPI(
        title=f"{settings.APP_NAME} API",
        version=settings.APP_VERSION,
        description=DESCRIPTION,
        docs_url="/api/docs", redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", settings.CSRF_HEADER],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(request_id=rid,
                                               path=request.url.path,
                                               method=request.method)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "path", "method")
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover
        log.exception("unhandled", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "internal_error",
                                "message": "internal error",
                                "request_id": getattr(request.state, "request_id", None)}},
        )

    from .api.routers import auth as auth_router
    from .api.routers import health as health_router
    from .api.routers import materials as materials_router

    app.include_router(health_router.router, prefix=settings.API_PREFIX)
    app.include_router(auth_router.router, prefix=settings.API_PREFIX)
    app.include_router(materials_router.router, prefix=settings.API_PREFIX)

    log.info("startup", version=settings.APP_VERSION,
             environment=settings.ENVIRONMENT, engine=backends.attribution())
    return app


app = create_app()
