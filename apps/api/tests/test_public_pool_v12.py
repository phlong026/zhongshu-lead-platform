from __future__ import annotations

import pytest
from sqlalchemy import func, select

from apps.api.src.core.auth import Principal
from apps.api.src.core.errors import AppError
from apps.api.src.core.models import AuditLog, Lead, Region, User
from apps.api.src.core.v12_enums import DuplicateDecision, LeadSourceKind, LeadV12Status
from apps.api.src.integrations.feishu import FeishuRecord
from apps.api.src.services.lead_supply_v12 import create_draft, submit_draft
from apps.api.src.services.public_pool_v12 import (
    PublicPoolTarget,
    create_public_pool_lead,
    import_feishu_customer_view,
    list_public_pool_leads,
    transfer_public_pool_lead,
    update_public_pool_lead,
)


def _principal(user_id: str, *permissions: str) -> Principal:
    return Principal(
        user_id=user_id,
        display_name="公海池测试运营",
        company_id=None,
        role_codes=frozenset({"OPERATION"}),
        permission_codes=frozenset(permissions),
        session_version=1,
    )


def _operation(db) -> tuple[User, Principal]:
    user = User(display_name="公海池测试运营", status="ACTIVE")
    db.add(user)
    db.flush()
    return user, _principal(user.id, "lead.manual.manage")


def _seed_region(db) -> None:
    db.add(Region(code="420100", name="武汉市", level="CITY", aliases=[], active=True))
    db.flush()


def _complete_values(phone: str = "13800138000") -> dict:
    return {
        "customer_name": "张先生",
        "phone": phone,
        "province": "湖北省",
        "city": "武汉市",
        "region_code": "420100",
        "source_channel": "OTHER",
        "source_detail": "飞书客户视图",
        "consent_confirmed": True,
    }


class FakeCustomerViewClient:
    def __init__(self, records: list[FeishuRecord]) -> None:
        self.records = records
        self.resolved_view_names: list[str] = []
        self.iterated_view_ids: list[str] = []
        self.writeback_calls = 0

    def resolve_view_id(self, view_name: str) -> str:
        self.resolved_view_names.append(view_name)
        return "view-customer"

    def iter_records(self, *, view_id: str, page_size: int, max_pages: int):
        self.iterated_view_ids.append(view_id)
        yield from self.records

    def write_back(self, record_id: str, fields: dict) -> None:
        self.writeback_calls += 1
        raise AssertionError("一期导入不得回写飞书")


def test_manual_and_inline_entries_share_public_pool_and_transfer_revalidates(db) -> None:
    _seed_region(db)
    _, principal = _operation(db)
    lead = create_public_pool_lead(
        db,
        principal=principal,
        values={"customer_name": "待补资料客户", "phone": "138 0013 8000"},
    )

    assert lead.status == LeadV12Status.DRAFT.value
    assert lead.source_kind == LeadSourceKind.PLATFORM_MANUAL.value
    assert lead.pending_reason == "PUBLIC_POOL_INCOMPLETE"
    assert set(lead.raw_payload["public_pool_validation_errors"]) >= {
        "region_code",
        "source_channel",
        "consent_confirmed",
    }

    incomplete, incomplete_total = list_public_pool_leads(
        db,
        completeness="INCOMPLETE",
    )
    assert incomplete_total == 1
    assert [item.id for item in incomplete] == [lead.id]

    blocked = transfer_public_pool_lead(db, lead=lead, principal=principal)
    assert blocked.transferred is False
    assert set(blocked.validation_errors) >= {
        "region_code",
        "source_channel",
        "consent_confirmed",
    }
    assert lead.status == LeadV12Status.DRAFT.value

    lead.region_code = "420100"
    lead.city = "武汉市"
    lead.source_channel = "OTHER"
    lead.source_detail = "线下活动"
    lead.consent_confirmed = True
    transferred = transfer_public_pool_lead(db, lead=lead, principal=principal)

    assert transferred.transferred is True
    assert transferred.validation_errors == {}
    assert lead.status == LeadV12Status.READY_DISPATCH.value


def test_editing_public_pool_lead_refreshes_completeness_immediately(db) -> None:
    _seed_region(db)
    _, principal = _operation(db)
    lead = create_public_pool_lead(
        db,
        principal=principal,
        values={"customer_name": "待补资料客户", "phone": "13800138010"},
    )

    update_public_pool_lead(
        db,
        lead=lead,
        principal=principal,
        values={
            "region_code": "420100",
            "city": "武汉市",
            "source_channel": "OTHER",
            "source_detail": "线下活动",
            "consent_confirmed": True,
        },
    )

    assert lead.pending_reason is None
    assert "public_pool_validation_errors" not in lead.raw_payload
    complete, complete_total = list_public_pool_leads(db, completeness="COMPLETE")
    assert complete_total == 1
    assert [item.id for item in complete] == [lead.id]


def test_public_pool_completeness_filter_recognizes_preexisting_manual_drafts(db) -> None:
    _, principal = _operation(db)
    legacy_draft = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.PLATFORM_MANUAL,
        values={"customer_name": "历史未补资料客户"},
    )
    assert legacy_draft.pending_reason is None

    incomplete, incomplete_total = list_public_pool_leads(
        db,
        completeness="INCOMPLETE",
    )

    assert incomplete_total == 1
    assert [item.id for item in incomplete] == [legacy_draft.id]


def test_feishu_dispatch_target_retains_incomplete_rows_and_is_idempotent(db, monkeypatch) -> None:
    import apps.api.src.services.public_pool_v12 as module

    _seed_region(db)
    _, principal = _operation(db)
    monkeypatch.setattr(module.settings, "feishu_app_token", "base-token")
    monkeypatch.setattr(module.settings, "feishu_table_id", "table-customer")
    monkeypatch.setattr(module.settings, "feishu_view_id", "")
    monkeypatch.setattr(module.settings, "feishu_view_name", "客户视图")
    monkeypatch.setattr(module.settings, "feishu_sync_page_size", 200)
    monkeypatch.setattr(module.settings, "feishu_sync_max_pages", 20)
    client = FakeCustomerViewClient(
        [
            FeishuRecord(
                record_id="rec-complete",
                fields={
                    "客户姓名": "完整客户",
                    "手机号": "+86 138-0013-8001",
                    "市": "武汉市",
                    "地区编码": "420100",
                    "来源渠道": "OTHER",
                    "具体来源": "飞书转介绍",
                    "已获客户授权": True,
                },
            ),
            FeishuRecord(
                record_id="rec-incomplete",
                fields={"客户姓名": "缺地区客户", "手机号": "13800138002"},
            ),
        ]
    )

    first = import_feishu_customer_view(
        db,
        principal=principal,
        target=PublicPoolTarget.DISPATCH_POOL,
        client=client,
    )
    db.commit()

    assert first.total_count == 2
    assert first.created_count == 2
    assert first.dispatch_pool_count == 1
    assert first.public_pool_count == 1
    assert first.skipped_count == 0
    assert client.resolved_view_names == ["客户视图"]
    assert client.iterated_view_ids == ["view-customer"]
    assert client.writeback_calls == 0

    complete = db.scalar(select(Lead).where(Lead.source_record_id == "rec-complete"))
    incomplete = db.scalar(select(Lead).where(Lead.source_record_id == "rec-incomplete"))
    assert complete is not None and complete.status == LeadV12Status.READY_DISPATCH.value
    assert incomplete is not None and incomplete.status == LeadV12Status.DRAFT.value
    assert incomplete.pending_reason == "PUBLIC_POOL_INCOMPLETE"
    assert complete.raw_payload["feishu_imported_field_names"]
    assert "13800138001" not in str(complete.raw_payload)
    assert "完整客户" not in str(complete.raw_payload)

    second = import_feishu_customer_view(
        db,
        principal=principal,
        target=PublicPoolTarget.DISPATCH_POOL,
        client=client,
    )
    db.commit()

    assert second.created_count == 0
    assert second.skipped_count == 2
    assert db.scalar(select(func.count(Lead.id)).where(Lead.source_kind == LeadSourceKind.FEISHU_IMPORT.value)) == 2


def test_public_pool_import_normalizes_phone_and_records_duplicate_without_dispatch(db, monkeypatch) -> None:
    import apps.api.src.services.public_pool_v12 as module

    _seed_region(db)
    _, principal = _operation(db)
    existing = create_draft(
        db,
        principal=principal,
        source_kind=LeadSourceKind.PLATFORM_MANUAL,
        values=_complete_values("13800138003"),
    )
    submit_draft(db, lead=existing, principal=principal)
    db.commit()

    monkeypatch.setattr(module.settings, "feishu_app_token", "base-token")
    monkeypatch.setattr(module.settings, "feishu_table_id", "table-customer")
    monkeypatch.setattr(module.settings, "feishu_view_id", "view-customer")
    monkeypatch.setattr(module.settings, "feishu_view_name", "客户视图")
    client = FakeCustomerViewClient(
        [
            FeishuRecord(
                record_id="rec-duplicate-phone",
                fields={
                    "客户姓名": "重复手机号客户",
                    "手机号": "+86 138 0013 8003",
                    "市": "武汉市",
                    "地区编码": "420100",
                    "来源渠道": "OTHER",
                    "具体来源": "飞书客户视图",
                    "已获客户授权": True,
                },
            )
        ]
    )

    result = import_feishu_customer_view(
        db,
        principal=principal,
        target=PublicPoolTarget.PUBLIC_POOL,
        client=client,
    )
    db.commit()

    imported = db.scalar(select(Lead).where(Lead.source_record_id == "rec-duplicate-phone"))
    assert result.duplicate_count == 1
    assert result.public_pool_count == 1
    assert imported is not None
    assert imported.status == LeadV12Status.DRAFT.value
    assert imported.duplicate_status == DuplicateDecision.HARD_DUPLICATE.value


def test_feishu_import_rejects_a_configured_view_id_that_is_not_customer_view(db, monkeypatch) -> None:
    import apps.api.src.services.public_pool_v12 as module

    _, principal = _operation(db)
    monkeypatch.setattr(module.settings, "feishu_app_token", "base-token")
    monkeypatch.setattr(module.settings, "feishu_table_id", "table-customer")
    monkeypatch.setattr(module.settings, "feishu_view_id", "view-wrong")
    monkeypatch.setattr(module.settings, "feishu_view_name", "客户视图")
    client = FakeCustomerViewClient([])

    with pytest.raises(AppError) as error:
        import_feishu_customer_view(
            db,
            principal=principal,
            target=PublicPoolTarget.PUBLIC_POOL,
            client=client,
        )

    assert error.value.code == "FEISHU_VIEW_CONFIG_MISMATCH"
    assert client.resolved_view_names == ["客户视图"]
    assert client.iterated_view_ids == []


def test_public_pool_http_is_shared_by_admin_and_operation_but_forbidden_to_franchise(
    api_client,
    monkeypatch,
) -> None:
    client, factory = api_client

    def login(username: str, password: str) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200, response.text
        token = response.cookies.get("access_token")
        assert token
        return {"Authorization": f"Bearer {token}"}

    admin = login("admin", "Admin123!")
    operation = login("operation", "Operation123!")
    franchise = login("franchise_demo", "Franchise123!")

    created = client.post(
        "/api/v1/v1.2/public-pool/leads",
        headers=operation,
        json={
            "customer_name": "权限验收客户",
            "phone": "13800138011",
            "region_code": "310000",
            "city": "上海市",
            "source_channel": "OTHER",
            "source_detail": "权限验收",
            "consent_confirmed": True,
        },
    )
    assert created.status_code == 200, created.text

    admin_page = client.get("/api/v1/v1.2/public-pool/leads", headers=admin)
    operation_page = client.get("/api/v1/v1.2/public-pool/leads", headers=operation)
    forbidden_page = client.get("/api/v1/v1.2/public-pool/leads", headers=franchise)

    assert admin_page.status_code == 200
    assert operation_page.status_code == 200
    assert admin_page.json()["data"]["total"] == 1
    assert operation_page.json()["data"]["total"] == 1
    assert forbidden_page.status_code == 403

    lead_id = created.json()["data"]["id"]
    transferred = client.post(
        f"/api/v1/v1.2/public-pool/leads/{lead_id}/transfer-to-dispatch",
        headers=operation,
    )
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["data"]["transferred"] is True

    with factory() as session:
        actions = list(
            session.scalars(
                select(AuditLog.action)
                .where(AuditLog.resource_id == lead_id)
                .order_by(AuditLog.created_at)
            ).all()
        )
    assert actions == ["V12_PUBLIC_POOL_LEAD_CREATE", "V12_PUBLIC_POOL_TRANSFER"]

    import apps.api.src.services.public_pool_v12 as module

    feishu = FakeCustomerViewClient(
        [
            FeishuRecord(
                record_id="rec-http-audit",
                fields={"客户姓名": "导入审计客户", "手机号": "13800138012"},
            )
        ]
    )
    monkeypatch.setattr(module.settings, "feishu_app_token", "base-http-audit")
    monkeypatch.setattr(module.settings, "feishu_table_id", "table-http-audit")
    monkeypatch.setattr(module.settings, "feishu_view_id", "")
    monkeypatch.setattr(module.settings, "feishu_view_name", "客户视图")
    monkeypatch.setattr(module, "FeishuClient", lambda: feishu)

    imported = client.post(
        "/api/v1/v1.2/public-pool/feishu/import",
        headers=operation,
        json={"target_pool": "PUBLIC_POOL"},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["data"]["created_count"] == 1
    assert feishu.writeback_calls == 0

    with factory() as session:
        import_audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "V12_PUBLIC_POOL_FEISHU_IMPORT")
        )
    assert import_audit is not None
