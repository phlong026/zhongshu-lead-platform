from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path

from anyio.to_thread import current_default_thread_limiter
from fastapi import Cookie, Depends, FastAPI
from fastapi.responses import RedirectResponse
from jwt import InvalidTokenError
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core.auth import get_valid_session_user
from .core.config import get_settings
from .core.database import SessionLocal, get_db, init_database
from .core.errors import register_error_handlers
from .core.in_flight import InFlightLimitMiddleware
from .core.legacy_guard import LegacyWriteGuardMiddleware
from .core.logging import configure_logging
from .core.production import validate_production_settings
from .core.request_context import RequestContextMiddleware
from .core.security import decode_access_token
from .routers import (
    admin,
    admin_meta,
    auth,
    claim,
    companies,
    dispatch,
    followups,
    invite_preview,
    leads,
    master_data,
    notifications,
    points,
    returns,
    users,
    v12_admin,
    v12_dispatch,
    v12_insights,
    v12_lead_supply,
    v12_returns,
    v12_rewards,
    v12_supplier_review,
    verification,
)
from .services.rbac import seed_rbac
from .services.storage import get_storage

settings = get_settings()
configure_logging()
ROOT = Path(__file__).resolve().parents[3]


@asynccontextmanager
async def lifespan(_: FastAPI):
    current_default_thread_limiter().total_tokens = settings.sync_threadpool_tokens
    if settings.app_env.lower() == "production":
        validation = validate_production_settings(settings)
        if not validation.valid:
            raise RuntimeError("生产环境配置校验失败：" + "；".join(validation.errors))
    init_database()
    with SessionLocal() as db:
        seed_rbac(db)
        db.commit()
    yield


app = FastAPI(
    title="合家美宅客资审核、派发与积分管理平台 API",
    version=settings.app_version,
    lifespan=lifespan,
)
app.add_middleware(LegacyWriteGuardMiddleware)
app.add_middleware(
    InFlightLimitMiddleware,
    limit=settings.max_in_flight_requests,
    queue_timeout_seconds=settings.in_flight_queue_timeout_seconds,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)

api_prefix = "/api/v1"
app.include_router(admin.router, prefix=api_prefix)
app.include_router(admin_meta.router, prefix=api_prefix)
app.include_router(auth.router, prefix=api_prefix)
app.include_router(invite_preview.router, prefix=api_prefix)
app.include_router(users.router, prefix=api_prefix)
app.include_router(companies.router, prefix=api_prefix)
app.include_router(leads.router, prefix=api_prefix)
app.include_router(verification.router, prefix=api_prefix)
app.include_router(points.router, prefix=api_prefix)
app.include_router(dispatch.router, prefix=api_prefix)
app.include_router(claim.router, prefix=api_prefix)
app.include_router(followups.router, prefix=api_prefix)
app.include_router(returns.router, prefix=api_prefix)
app.include_router(notifications.router, prefix=api_prefix)
app.include_router(master_data.router, prefix=api_prefix)
app.include_router(v12_admin.router, prefix=api_prefix)
app.include_router(v12_lead_supply.router, prefix=api_prefix)
app.include_router(v12_supplier_review.router, prefix=api_prefix)
app.include_router(v12_dispatch.router, prefix=api_prefix)
app.include_router(v12_returns.router, prefix=api_prefix)
app.include_router(v12_rewards.router, prefix=api_prefix)
app.include_router(v12_insights.router, prefix=api_prefix)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "zhongshu-lead-platform", "version": settings.app_version, "environment": settings.app_env}


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "alive", "version": settings.app_version}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    storage = "s3-ready" if settings.object_storage_backend.lower() == "s3" else "local-mounted"
    if settings.object_storage_backend.lower() == "s3":
        get_storage().check_readiness()
    else:
        storage_root = Path(settings.object_storage_dir)
        storage_root.mkdir(parents=True, exist_ok=True)
        if not storage_root.is_dir() or not os.access(storage_root, os.W_OK):
            raise RuntimeError("对象存储目录不可写")
    return {"status": "ready", "database": "ok", "storage": storage, "version": settings.app_version}


def _has_valid_web_session(db: Session, access_token: str | None) -> bool:
    if not access_token:
        return False
    try:
        payload = decode_access_token(access_token)
    except InvalidTokenError:
        return False
    return get_valid_session_user(db, payload.get("sub"), payload.get("sv")) is not None


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_entry(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = "/admin/v12-operations.html" if _has_valid_web_session(db, access_token) else "/admin/index.html"
    return RedirectResponse(url=target, status_code=302)


@app.get("/h5", include_in_schema=False)
@app.get("/h5/", include_in_schema=False)
def h5_entry(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = "/h5/v12-workbench.html" if _has_valid_web_session(db, access_token) else "/h5/index.html"
    return RedirectResponse(url=target, status_code=302)


@app.get("/admin/legacy", include_in_schema=False)
def admin_legacy_entry() -> RedirectResponse:
    return RedirectResponse(url="/admin/index.html", status_code=302)


@app.get("/h5/legacy", include_in_schema=False)
def h5_legacy_entry() -> RedirectResponse:
    return RedirectResponse(url="/h5/index.html", status_code=302)


for route, directory, name in [
    ("/h5", ROOT / "apps" / "h5" / "public", "h5"),
    ("/call", ROOT / "apps" / "call-h5" / "public", "call-h5"),
    ("/admin", ROOT / "apps" / "admin" / "public", "admin"),
]:
    directory.mkdir(parents=True, exist_ok=True)
    app.mount(route, StaticFiles(directory=directory, html=True), name=name)
