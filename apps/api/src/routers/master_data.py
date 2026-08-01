from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.auth import require_permissions
from ..core.database import get_db
from ..core.models import DictionaryItem, Region
from ..core.responses import ok, page
from ..schemas.company import DictionaryItemBody
from ..services.audit import write_audit

router = APIRouter(prefix="/master-data", tags=["master-data"])


@router.get("/regions")
def regions(request: Request, db: Session = Depends(get_db), parent_code: str | None = None, level: str | None = None):
    stmt = select(Region).where(Region.active.is_(True))
    if parent_code is not None:
        stmt = stmt.where(Region.parent_code == parent_code)
    if level:
        stmt = stmt.where(Region.level == level)
    items = db.scalars(stmt.order_by(Region.code)).all()
    return ok(request, [{"code": x.code, "name": x.name, "level": x.level, "parent_code": x.parent_code, "aliases": x.aliases} for x in items])


@router.get("/dictionaries/{domain}")
def dictionary(request: Request, domain: str, db: Session = Depends(get_db), active_only: bool = True):
    stmt = select(DictionaryItem).where(DictionaryItem.domain == domain)
    if active_only:
        stmt = stmt.where(DictionaryItem.active.is_(True))
    items = db.scalars(stmt.order_by(DictionaryItem.version.desc(), DictionaryItem.sort_order, DictionaryItem.code)).all()
    return ok(request, [{"id": x.id, "code": x.code, "label": x.label, "version": x.version, "active": x.active, "metadata": x.metadata_json} for x in items])


@router.post("/dictionaries")
def create_dictionary_item(
    body: DictionaryItemBody,
    request: Request,
    principal=Depends(require_permissions("*")),
    db: Session = Depends(get_db),
):
    latest = db.scalar(select(func.max(DictionaryItem.version)).where(DictionaryItem.domain == body.domain, DictionaryItem.code == body.code)) or 0
    item = DictionaryItem(domain=body.domain, code=body.code, label=body.label, version=latest + 1, sort_order=body.sort_order, metadata_json=body.metadata, active=body.active)
    db.add(item)
    db.flush()
    write_audit(db, principal=principal, action="DICTIONARY_CREATE", resource_type="dictionary", resource_id=item.id, after={"domain": item.domain, "code": item.code, "version": item.version}, request_id=request.state.request_id)
    db.commit()
    return ok(request, {"id": item.id, "version": item.version})
