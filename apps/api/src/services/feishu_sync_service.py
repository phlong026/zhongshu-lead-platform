from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.models import Lead, SyncBatch
from ..integrations.feishu import FeishuClient, FeishuRecord
from .lead_service import import_records

settings = get_settings()

DEFAULT_FIELD_MAPPING = {
    "customer_name": "客户姓名",
    "phone": "手机号",
    "province": "省",
    "city": "市",
    "district": "区县",
    "region_code": "地区编码",
    "category_code": "业务类目",
    "brand_code": "品牌",
    "source_channel": "来源渠道",
    "need_summary": "客户需求",
    "budget_min": "预算下限",
    "budget_max": "预算上限",
    "acquisition_cost": "获客成本",
}


def configured_mapping() -> dict[str, str]:
    raw = getattr(settings, "feishu_field_mapping_json", "")
    if not raw:
        return DEFAULT_FIELD_MAPPING.copy()
    try:
        custom = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_FIELD_MAPPING.copy()
    return {**DEFAULT_FIELD_MAPPING, **{str(k): str(v) for k, v in custom.items() if v}}


def _require_legacy_import_enabled() -> None:
    if not settings.legacy_write_enabled:
        raise AppError(
            "LEGACY_WRITE_DISABLED",
            "V1.0.1 飞书新增客资导入已停用，请使用 V1.2 平台录客或供应商供客",
            410,
        )


def fetch_and_import_feishu(
    db: Session,
    *,
    requested_by: str | None = None,
    client: FeishuClient | None = None,
) -> tuple[SyncBatch, list[FeishuRecord]]:
    _require_legacy_import_enabled()
    FeishuClient.ensure_enabled()
    adapter = client or FeishuClient()
    records = list(
        adapter.iter_records(
            page_size=getattr(settings, "feishu_sync_page_size", 200),
            max_pages=getattr(settings, "feishu_sync_max_pages", 100),
        )
    )
    batch = import_records(
        db,
        records,
        configured_mapping(),
        app_token=settings.feishu_app_token,
        table_id=settings.feishu_table_id,
        requested_by=requested_by,
    )
    return batch, records


def writeback_feishu_results(
    db: Session,
    records: list[FeishuRecord],
    *,
    client: FeishuClient | None = None,
) -> dict[str, int]:
    _require_legacy_import_enabled()
    FeishuClient.ensure_enabled()
    if not getattr(settings, "feishu_writeback_enabled", True):
        return {"written": 0, "failed": 0}
    adapter = client or FeishuClient()
    written = 0
    failed = 0
    for record in records:
        lead = db.scalar(
            select(Lead).where(
                Lead.source_app_token == settings.feishu_app_token,
                Lead.source_table_id == settings.feishu_table_id,
                Lead.source_record_id == record.record_id,
            )
        )
        if not lead:
            continue
        try:
            adapter.write_back(
                record.record_id,
                {
                    "系统客资ID": lead.id,
                    "同步状态": "异常" if lead.status == "IMPORT_ERROR" else "已导入",
                    "派发状态": lead.status,
                    "异常原因": lead.pending_reason or "",
                },
            )
            written += 1
        except Exception:
            failed += 1
    return {"written": written, "failed": failed}
