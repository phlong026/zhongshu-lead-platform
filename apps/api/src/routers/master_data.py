from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from ..core.auth import require_permissions
from ..core.database import get_db
from ..core.models import DictionaryItem, Region
from ..core.responses import ok, page
from ..schemas.company import DictionaryItemBody
from ..services.audit import write_audit
from ..services.china_regions import region_tree

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


def _region_path(
    regions_by_code: dict[str, Region],
    region: Region,
) -> list[dict[str, str]]:
    path: list[dict[str, str]] = []
    current: Region | None = region
    visited: set[str] = set()
    while current is not None and current.code not in visited:
        visited.add(current.code)
        path.append({"code": current.code, "name": current.name, "level": current.level})
        current = regions_by_code.get(current.parent_code or "")
    return list(reversed(path))


@router.get("/regions/search")
def search_regions(
    request: Request,
    db: Session = Depends(get_db),
    keyword: str = Query(min_length=1, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
):
    normalized = keyword.strip()
    if not normalized:
        return ok(request, [])
    rows = db.scalars(
        select(Region)
        .where(
            Region.active.is_(True),
            or_(
                Region.name.contains(normalized),
                cast(Region.aliases, String).contains(normalized),
            ),
        )
        .order_by(Region.level, Region.code)
        .limit(limit)
    ).all()
    regions_by_code = {region.code: region for region in rows}
    unresolved_parent_codes = {
        region.parent_code
        for region in rows
        if region.parent_code and region.parent_code not in regions_by_code
    }
    while unresolved_parent_codes:
        parents = db.scalars(
            select(Region).where(Region.code.in_(unresolved_parent_codes))
        ).all()
        if not parents:
            break
        regions_by_code.update({region.code: region for region in parents})
        unresolved_parent_codes = {
            region.parent_code
            for region in parents
            if region.parent_code and region.parent_code not in regions_by_code
        }
    items = []
    for region in rows:
        path = _region_path(regions_by_code, region)
        items.append(
            {
                "code": region.code,
                "name": region.name,
                "level": region.level,
                "parent_code": region.parent_code,
                "path": path,
                "path_codes": [item["code"] for item in path],
                "path_label": " · ".join(item["name"] for item in path),
            }
        )
    return ok(request, items)


@router.get("/region-tree")
def nationwide_region_tree(request: Request, response: Response):
    response.headers["cache-control"] = "public, max-age=86400"
    return ok(request, region_tree())


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
