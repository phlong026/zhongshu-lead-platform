from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .core.config import get_settings
from .core.database import SessionLocal, init_database
from .core.errors import register_error_handlers
from .core.request_context import RequestContextMiddleware
from .routers import admin, auth, claim, companies, dispatch, followups, leads, master_data, notifications, points, returns, users, verification
from .services.rbac import seed_rbac

settings = get_settings()
ROOT = Path(__file__).resolve().parents[3]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    with SessionLocal() as db:
        seed_rbac(db)
        db.commit()
    yield


app = FastAPI(
    title="众墅之家客资审核、派发与积分管理平台 API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
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
app.include_router(auth.router, prefix=api_prefix)
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "zhongshu-lead-platform"}


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


for route, directory, name in [
    ("/h5", ROOT / "apps" / "h5" / "public", "h5"),
    ("/call", ROOT / "apps" / "call-h5" / "public", "call-h5"),
    ("/admin", ROOT / "apps" / "admin" / "public", "admin"),
]:
    directory.mkdir(parents=True, exist_ok=True)
    app.mount(route, StaticFiles(directory=directory, html=True), name=name)
