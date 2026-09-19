"""Liveness, readiness and the system-status panel an admin needs.

`/health` answers "is the process up". `/ready` answers "can it actually serve",
which means the database answers and the configured matching backends resolved.
A readiness probe that returns 200 while the engine is silently degraded would
defeat the point of MATCHING_STRICT, so degradation is reported explicitly.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from ...config import settings
from ...db import database_healthy
from ...matching.backends import resolve_all
from ..deps import require_admin

router = APIRouter(tags=["system"])
_STARTED = time.time()


@router.get("/health", summary="Liveness")
def health() -> dict:
    return {"status": "ok", "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "uptime_seconds": round(time.time() - _STARTED, 1)}


@router.get("/ready", summary="Readiness")
def ready() -> dict:
    db_ok, db_detail = database_healthy()
    try:
        backends = resolve_all(strict=False).as_dict()
        engine_ok = not (settings.strict_backends and backends["degraded"])
    except Exception as exc:  # pragma: no cover
        backends, engine_ok = {"error": str(exc)[:200]}, False
    ok = db_ok and engine_ok
    return {"status": "ready" if ok else "not_ready",
            "database": {"ok": db_ok, "detail": db_detail},
            "engine": backends,
            "version": settings.APP_VERSION}


@router.get("/system/status", summary="Full system status (admin)",
            dependencies=[Depends(require_admin)])
def system_status() -> dict:
    db_ok, db_detail = database_healthy()
    llm = {"enabled": settings.OLLAMA_ENABLED, "model": settings.OLLAMA_MODEL,
           "base_url": settings.OLLAMA_BASE_URL, "reachable": None,
           "role": "structured attribute extraction only — never a decision maker"}
    if settings.OLLAMA_ENABLED:
        try:
            import httpx
            r = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3.0)
            llm["reachable"] = r.status_code == 200
            if r.status_code == 200:
                llm["models"] = [m.get("name") for m in r.json().get("models", [])]
        except Exception as exc:
            llm["reachable"] = False
            llm["error"] = str(exc)[:160]
    return {"app": {"name": settings.APP_NAME, "version": settings.APP_VERSION,
                    "environment": settings.ENVIRONMENT},
            "database": {"ok": db_ok, "detail": db_detail,
                         "url_host": settings.DATABASE_URL.split("@")[-1]},
            "engine": resolve_all(strict=False).as_dict(),
            "config": settings.describe_backends(),
            "llm": llm}
