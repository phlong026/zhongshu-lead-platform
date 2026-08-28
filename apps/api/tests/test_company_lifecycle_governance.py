from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from apps.api.src.core.models import (
    Assignment,
    AuditLog,
    Company,
    CompanyAccountRequest,
    FollowUp,
    InviteToken,
    Lead,
    Notification,
    NotificationOutbox,
    PointsAccount,
    PointsLedger,
    ReturnRequest,
    User,
    WechatIdentity,
)
from apps.api.src.core.models_v12 import SupplierLeadReward
from apps.api.src.services.auth_service import bind_wechat_by_invite
from apps.api.src.services.outbox_worker import process_outbox


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.cookies.get('access_token')}"}


def _create_company(
    client,
    headers: dict[str, str],
    *,
    name: str,
    is_test: bool,
) -> str:
    response = client.post(
        "/api/v1/companies/simple",
        headers=headers,
        json={
            "name": name,
            "owner_name": "测试负责人",
            "primary_city_code": "310000",
            "district_codes": ["310104"],
            "serve_all_districts": False,
            "is_test": is_test,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def _bind_company(client, factory, headers: dict[str, str], company_id: str, openid: str) -> str:
    response = client.post(
        f"/api/v1/auth/companies/{company_id}/invites",
        headers=headers,
        json={"expires_hours": 72},
    )
    assert response.status_code == 200, response.text
    raw_token = response.json()["data"]["token"]
    with factory() as db:
        user, _ = bind_wechat_by_invite(db, raw_token, openid, "微信负责人")
        db.commit()
        return user.id


def _disable_company(client, headers: dict[str, str], company_id: str) -> None:
    response = client.patch(
        f"/api/v1/companies/{company_id}",
        headers=headers,
        json={"status": "DISABLED", "reason": "业务隔离"},
    )
    assert response.status_code == 200, response.text


def test_company_disable_isolates_business_without_releasing_wechat(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    company_id = _create_company(
        client,
        admin,
        name="停用隔离测试加盟商",
        is_test=False,
    )
    user_id = _bind_company(client, factory, admin, company_id, "openid-disable-kept")

    with factory() as db:
        session_version = db.get(User, user_id).session_version

    _disable_company(client, admin, company_id)

    with factory() as db:
        company = db.get(Company, company_id)
        user = db.get(User, user_id)
        identity = db.scalar(
            select(WechatIdentity).where(WechatIdentity.openid == "openid-disable-kept")
        )
        assert company is not None
        assert company.status == "DISABLED"
        assert company.primary_user_id == user_id
        assert user is not None and user.session_version == session_version + 1
        assert identity is not None and identity.user_id == user_id


def test_company_disable_revokes_invites_and_cancels_stale_delivery(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    company_id = _create_company(
        client,
        operation,
        name="停用邀请隔离测试",
        is_test=True,
    )
    invite_response = client.post(
        f"/api/v1/auth/companies/{company_id}/invites",
        headers=operation,
        json={"expires_hours": 72},
    )
    assert invite_response.status_code == 200, invite_response.text
    invite_id = invite_response.json()["data"]["invite_id"]

    _disable_company(client, operation, company_id)

    with factory() as db:
        invite = db.get(InviteToken, invite_id)
        outbox = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_type == "invite",
                NotificationOutbox.aggregate_id == invite_id,
            )
        )
        assert invite is not None and invite.revoked_at is not None
        assert outbox is not None and outbox.status == "CANCELLED"

        # 模拟 worker 在停用交易前已读到的旧队列状态；发送边界仍必须二次校验。
        outbox.status = "PENDING"
        db.commit()
        result = process_outbox(db)
        db.commit()
        assert result["cancelled"] == 1
        assert outbox.status == "CANCELLED"


def test_unbind_releases_wechat_and_allows_new_company_binding(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    old_company_id = _create_company(
        client,
        operation,
        name="原测试加盟商",
        is_test=True,
    )
    new_company_id = _create_company(
        client,
        operation,
        name="新测试加盟商",
        is_test=True,
    )
    old_user_id = _bind_company(
        client,
        factory,
        operation,
        old_company_id,
        "openid-move-owner",
    )

    active_response = client.post(
        f"/api/v1/companies/{old_company_id}/wechat-binding/unbind",
        headers=operation,
        json={"confirm_name": "原测试加盟商", "reason": "负责人改签新公司"},
    )
    assert active_response.status_code == 409, active_response.text
    assert active_response.json()["code"] == "COMPANY_MUST_BE_DISABLED"

    _disable_company(client, operation, old_company_id)
    response = client.post(
        f"/api/v1/companies/{old_company_id}/wechat-binding/unbind",
        headers=operation,
        json={"confirm_name": "原测试加盟商", "reason": "负责人改签新公司"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["unbound_user_id"] == old_user_id

    new_user_id = _bind_company(
        client,
        factory,
        operation,
        new_company_id,
        "openid-move-owner",
    )
    assert new_user_id != old_user_id

    with factory() as db:
        old_company = db.get(Company, old_company_id)
        new_company = db.get(Company, new_company_id)
        old_user = db.get(User, old_user_id)
        identity = db.scalar(
            select(WechatIdentity).where(WechatIdentity.openid == "openid-move-owner")
        )
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "COMPANY_WECHAT_UNBIND",
                AuditLog.resource_id == old_company_id,
            )
        )
        assert old_company is not None and old_company.primary_user_id is None
        assert new_company is not None and new_company.primary_user_id == new_user_id
        assert old_user is not None and old_user.status == "DISABLED"
        assert identity is not None and identity.user_id == new_user_id
        assert audit is not None
        assert audit.metadata_json["reason"] == "负责人改签新公司"


def test_delete_endpoint_does_not_remove_disabled_test_company_or_binding(api_client) -> None:
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    company_id = _create_company(
        client,
        operation,
        name="可删除测试主体",
        is_test=True,
    )
    owner_user_id = _bind_company(
        client,
        factory,
        operation,
        company_id,
        "openid-delete-test",
    )
    _disable_company(client, operation, company_id)

    response = client.request(
        "DELETE",
        f"/api/v1/companies/{company_id}",
        headers=operation,
        json={"confirm_name": "可删除测试主体", "reason": "清理历史联测数据"},
    )
    assert response.status_code == 405, response.text

    with factory() as db:
        assert db.get(Company, company_id) is not None
        assert db.scalar(
            select(WechatIdentity).where(WechatIdentity.openid == "openid-delete-test")
        ) is not None
        owner = db.get(User, owner_user_id)
        assert owner is not None
        assert owner.company_id == company_id
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "COMPANY_TEST_DELETE",
                AuditLog.resource_id == company_id,
            )
        )
        assert audit is None


def test_existing_zero_business_company_requires_superadmin_to_mark_as_test(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    operation = _login(client, "operation", "Operation123!")
    company_id = _create_company(
        client,
        admin,
        name="历史联测主体",
        is_test=False,
    )
    _disable_company(client, admin, company_id)

    forbidden = client.post(
        f"/api/v1/companies/{company_id}/mark-test",
        headers=operation,
        json={"confirm_name": "历史联测主体", "reason": "清理历史联测数据"},
    )
    assert forbidden.status_code == 403, forbidden.text

    response = client.post(
        f"/api/v1/companies/{company_id}/mark-test",
        headers=admin,
        json={"confirm_name": "历史联测主体", "reason": "清理历史联测数据"},
    )
    assert response.status_code == 200, response.text

    with factory() as db:
        company = db.get(Company, company_id)
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "COMPANY_TEST_MARK",
                AuditLog.resource_id == company_id,
            )
        )
        assert company is not None and company.is_test is True
        assert audit is not None
        assert audit.metadata_json["reason"] == "清理历史联测数据"


def test_superadmin_can_mark_but_cannot_delete_historical_test_company_with_points(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    company_id = _create_company(
        client,
        admin,
        name="历史有积分联测主体",
        is_test=False,
    )
    _disable_company(client, admin, company_id)
    with factory() as db:
        account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company_id))
        assert account is not None
        account.balance = 50
        db.add(
            PointsLedger(
                account_id=account.id,
                company_id=company_id,
                ledger_type="RECHARGE",
                delta=50,
                balance_after=50,
                business_type="RECHARGE",
                business_id="historical-test-recharge",
                idempotency_key="historical-test-recharge",
            )
        )
        db.commit()

    marked = client.post(
        f"/api/v1/companies/{company_id}/mark-test",
        headers=admin,
        json={"confirm_name": "历史有积分联测主体", "reason": "确认为历史联测账号"},
    )
    assert marked.status_code == 200, marked.text

    deleted = client.request(
        "DELETE",
        f"/api/v1/companies/{company_id}",
        headers=admin,
        json={"confirm_name": "历史有积分联测主体", "reason": "清理历史联测数据"},
    )
    assert deleted.status_code == 405, deleted.text
    with factory() as db:
        assert db.get(Company, company_id) is not None
        assert db.scalar(select(PointsLedger).where(PointsLedger.company_id == company_id)) is not None


def test_historical_company_with_platform_assignment_cannot_be_marked_as_test(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    company_id = _create_company(
        client,
        admin,
        name="与平台客资关联的主体",
        is_test=False,
    )
    with factory() as db:
        operator = db.scalar(select(User).where(User.username == "admin"))
        assert operator is not None
        lead = Lead(
            customer_name="平台客资",
            phone_encrypted="test-encrypted-phone",
            phone_hash="platform-cross-business-phone",
            status="READY_DISPATCH",
        )
        db.add(lead)
        db.flush()
        db.add(
            Assignment(
                lead_id=lead.id,
                company_id=company_id,
                status="PENDING_CLAIM",
                points_price=100,
                lead_snapshot={},
                assigned_by=operator.id,
            )
        )
        db.commit()

    _disable_company(client, admin, company_id)
    response = client.post(
        f"/api/v1/companies/{company_id}/mark-test",
        headers=admin,
        json={"confirm_name": "与平台客资关联的主体", "reason": "尝试标记为测试"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "COMPANY_TEST_DATA_CROSS_BUSINESS_BLOCKED"


def test_test_supplier_with_lead_dispatched_to_another_company_cannot_be_deleted(
    api_client,
) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    supplier_id = _create_company(
        client,
        admin,
        name="跨主体供资测试方",
        is_test=True,
    )
    receiver_id = _create_company(
        client,
        admin,
        name="真实接收方",
        is_test=False,
    )
    with factory() as db:
        operator = db.scalar(select(User).where(User.username == "admin"))
        assert operator is not None
        lead = Lead(
            customer_name="已派给其他主体的客资",
            phone_encrypted="test-encrypted-phone",
            phone_hash="cross-company-supplier-lead",
            status="CLAIMED",
            source_kind="SUPPLIER_H5",
            supplier_company_id=supplier_id,
        )
        db.add(lead)
        db.flush()
        db.add(
            Assignment(
                lead_id=lead.id,
                company_id=receiver_id,
                supplier_company_id=None,
                receiver_company_id=receiver_id,
                status="CLAIMED",
                points_price=100,
                claim_points=100,
                lead_snapshot={},
                assigned_by=operator.id,
            )
        )
        db.commit()

    _disable_company(client, admin, supplier_id)
    response = client.request(
        "DELETE",
        f"/api/v1/companies/{supplier_id}",
        headers=admin,
        json={"confirm_name": "跨主体供资测试方", "reason": "验证跨主体保护"},
    )
    assert response.status_code == 405, response.text


def test_test_company_with_return_or_followup_on_external_assignment_cannot_be_deleted(
    api_client,
) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    test_company_id = _create_company(
        client,
        admin,
        name="跨主体退回测试方",
        is_test=True,
    )
    receiver_id = _create_company(
        client,
        admin,
        name="跨主体退回接收方",
        is_test=False,
    )
    with factory() as db:
        operator = db.scalar(select(User).where(User.username == "admin"))
        assert operator is not None
        lead = Lead(
            customer_name="平台真实客资",
            phone_encrypted="test-encrypted-phone",
            phone_hash="cross-company-return-lead",
            status="CLAIMED",
        )
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=receiver_id,
            receiver_company_id=receiver_id,
            status="CLAIMED",
            points_price=100,
            claim_points=100,
            lead_snapshot={},
            assigned_by=operator.id,
        )
        db.add(assignment)
        db.flush()
        db.add_all(
            [
                FollowUp(
                    assignment_id=assignment.id,
                    company_id=test_company_id,
                    status="FOLLOWING",
                    note="不应随测试主体误删",
                    created_by=operator.id,
                ),
                ReturnRequest(
                    assignment_id=assignment.id,
                    lead_id=lead.id,
                    company_id=test_company_id,
                    reason_code="TEST_RETURN",
                    reason_version=1,
                    description="不应随测试主体误删",
                    status="DRAFT",
                    submitted_by=operator.id,
                ),
            ]
        )
        db.commit()

    _disable_company(client, admin, test_company_id)
    response = client.request(
        "DELETE",
        f"/api/v1/companies/{test_company_id}",
        headers=admin,
        json={"confirm_name": "跨主体退回测试方", "reason": "验证跨主体保护"},
    )
    assert response.status_code == 405, response.text


def test_test_marker_cannot_be_changed_through_general_company_update(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    company_id = _create_company(
        client,
        admin,
        name="正常主体不可改标记",
        is_test=False,
    )

    response = client.patch(
        f"/api/v1/companies/{company_id}",
        headers=admin,
        json={"is_test": True},
    )
    assert response.status_code == 422, response.text
    with factory() as db:
        company = db.get(Company, company_id)
        assert company is not None and company.is_test is False


def test_company_status_change_requires_an_auditable_reason(api_client) -> None:
    client, _ = api_client
    admin = _login(client, "admin", "Admin123!")
    company_id = _create_company(
        client,
        admin,
        name="启停理由校验主体",
        is_test=True,
    )

    response = client.patch(
        f"/api/v1/companies/{company_id}",
        headers=admin,
        json={"status": "DISABLED"},
    )
    assert response.status_code == 422, response.text

    disabled = client.patch(
        f"/api/v1/companies/{company_id}",
        headers=admin,
        json={"status": "DISABLED", "reason": "暂停联测主体"},
    )
    assert disabled.status_code == 200, disabled.text

    enabled_without_reason = client.patch(
        f"/api/v1/companies/{company_id}",
        headers=admin,
        json={"status": "ACTIVE"},
    )
    assert enabled_without_reason.status_code == 422, enabled_without_reason.text


def test_company_delete_endpoint_is_not_exposed_and_points_history_is_preserved(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    test_id = _create_company(
        client,
        admin,
        name="有积分流水测试主体",
        is_test=True,
    )
    _disable_company(client, admin, test_id)
    with factory() as db:
        account = db.scalar(
            select(PointsAccount).where(PointsAccount.company_id == test_id)
        )
        assert account is not None
        account.balance = 100
        db.add(
            PointsLedger(
                account_id=account.id,
                company_id=test_id,
                ledger_type="RECHARGE",
                delta=100,
                balance_after=100,
                business_type="RECHARGE",
                business_id="test-recharge",
                idempotency_key="test-company-delete-blocker",
            )
        )
        db.commit()

    deleted_response = client.request(
        "DELETE",
        f"/api/v1/companies/{test_id}",
        headers=admin,
        json={"confirm_name": "有积分流水测试主体", "reason": "尝试清理有业务数据"},
    )
    assert deleted_response.status_code == 405, deleted_response.text

    with factory() as db:
        assert db.get(Company, test_id) is not None
        assert db.scalar(select(PointsAccount).where(PointsAccount.company_id == test_id)) is not None
        assert db.scalar(select(PointsLedger).where(PointsLedger.company_id == test_id)) is not None


def test_delete_preserves_self_contained_test_company_business_history(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    company_id = _create_company(
        client,
        admin,
        name="全量清理测试主体",
        is_test=True,
    )
    owner_user_id = _bind_company(
        client,
        factory,
        admin,
        company_id,
        "openid-full-test-purge",
    )

    platform_notification_id = ""
    with factory() as db:
        operator = db.scalar(select(User).where(User.username == "admin"))
        account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company_id))
        assert operator is not None and account is not None

        lead = Lead(
            customer_name="测试客户",
            phone_encrypted="test-encrypted-phone",
            phone_hash="full-test-purge-phone",
            region_code="310104",
            category_code="OLD_RENOVATION",
            status="CLAIMED",
            source_kind="SUPPLIER_H5",
            submitter_user_id=owner_user_id,
            supplier_company_id=company_id,
        )
        db.add(lead)
        db.flush()
        assignment = Assignment(
            lead_id=lead.id,
            company_id=company_id,
            supplier_company_id=company_id,
            receiver_company_id=company_id,
            status="CLAIMED",
            points_price=100,
            claim_points=100,
            lead_snapshot={},
            assigned_by=operator.id,
        )
        db.add(assignment)
        db.flush()
        db.add(
            FollowUp(
                assignment_id=assignment.id,
                company_id=company_id,
                status="FOLLOWING",
                note="测试跟进",
                created_by=owner_user_id,
            )
        )
        db.add(
            ReturnRequest(
                assignment_id=assignment.id,
                lead_id=lead.id,
                company_id=company_id,
                reason_code="TEST_RETURN",
                reason_version=1,
                description="测试退回",
                status="DRAFT",
                submitted_by=owner_user_id,
            )
        )
        db.add(
            SupplierLeadReward(
                lead_id=lead.id,
                assignment_id=assignment.id,
                supplier_company_id=company_id,
                receiver_company_id=company_id,
                status="OBSERVING",
                claim_points=100,
                reward_ratio_bps=3000,
                reward_points=30,
                rule_version=1,
                rule_snapshot_json={"version": 1, "ratio_bps": 3000},
            )
        )
        account.balance = 70
        db.add(
            PointsLedger(
                account_id=account.id,
                company_id=company_id,
                ledger_type="RECHARGE",
                delta=100,
                balance_after=100,
                business_type="RECHARGE",
                business_id="full-test-purge-recharge",
                idempotency_key="full-test-purge-recharge",
            )
        )
        db.add(
            PointsLedger(
                account_id=account.id,
                company_id=company_id,
                ledger_type="CLAIM",
                delta=-30,
                balance_after=70,
                business_type="ASSIGNMENT",
                business_id=assignment.id,
                idempotency_key="full-test-purge-claim",
            )
        )
        platform_notification = Notification(
            user_id=operator.id,
            company_id=None,
            scene="COMPANY_TEST_MESSAGE",
            title="测试主体消息",
            body="该消息应随测试主体清理",
            deep_link=f"/admin/v12-operations.html?view=companies&id={company_id}",
            status="CREATED",
        )
        db.add(platform_notification)
        db.flush()
        platform_notification_id = platform_notification.id
        db.add(
            NotificationOutbox(
                event_key=f"company:{company_id}:test-message",
                event_type="COMPANY_TEST_MESSAGE",
                aggregate_type="profile",
                aggregate_id=company_id,
                payload={"notification_id": platform_notification.id},
                status="PENDING",
            )
        )
        db.commit()

    _disable_company(client, admin, company_id)
    response = client.request(
        "DELETE",
        f"/api/v1/companies/{company_id}",
        headers=admin,
        json={"confirm_name": "全量清理测试主体", "reason": "清理完整联测数据"},
    )
    assert response.status_code == 405, response.text

    with factory() as db:
        assert db.get(Company, company_id) is not None
        assert db.scalar(select(Lead).where(Lead.supplier_company_id == company_id)) is not None
        assert db.scalar(select(Assignment).where(Assignment.company_id == company_id)) is not None
        assert db.scalar(select(FollowUp).where(FollowUp.company_id == company_id)) is not None
        assert db.scalar(select(ReturnRequest).where(ReturnRequest.company_id == company_id)) is not None
        assert db.scalar(
            select(SupplierLeadReward).where(
                SupplierLeadReward.supplier_company_id == company_id
            )
        ) is not None
        assert db.scalar(select(PointsLedger).where(PointsLedger.company_id == company_id)) is not None
        assert db.scalar(select(PointsAccount).where(PointsAccount.company_id == company_id)) is not None
        assert db.get(Notification, platform_notification_id) is not None
        assert db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.aggregate_id == company_id
            )
        ) is not None


def test_company_delete_endpoint_preserves_account_application_history(api_client) -> None:
    client, factory = api_client
    admin = _login(client, "admin", "Admin123!")
    company_id = _create_company(
        client,
        admin,
        name="有账号申请的测试主体",
        is_test=True,
    )
    _disable_company(client, admin, company_id)

    with factory() as db:
        admin_user = db.scalar(select(User).where(User.username == "admin"))
        assert admin_user is not None
        db.add(
            CompanyAccountRequest(
                company_id=company_id,
                request_type="CREATE_EMPLOYEE",
                status="REJECTED",
                requested_by=admin_user.id,
                requested_username="historical_test_employee",
                requested_display_name="历史测试员工",
                reason="联测账号申请",
            )
        )
        db.commit()

    response = client.request(
        "DELETE",
        f"/api/v1/companies/{company_id}",
        headers=admin,
        json={"confirm_name": "有账号申请的测试主体", "reason": "尝试清理申请历史"},
    )
    assert response.status_code == 405, response.text
    with factory() as db:
        assert db.get(Company, company_id) is not None
        assert db.scalar(
            select(CompanyAccountRequest).where(
                CompanyAccountRequest.company_id == company_id
            )
        ) is not None


def test_company_lifecycle_mutations_require_platform_permission(api_client) -> None:
    client, _ = api_client
    admin = _login(client, "admin", "Admin123!")
    company_id = _create_company(
        client,
        admin,
        name="权限测试主体",
        is_test=True,
    )
    _disable_company(client, admin, company_id)
    franchise = _login(client, "franchise_demo", "Franchise123!")

    response = client.post(
        f"/api/v1/companies/{company_id}/wechat-binding/unbind",
        headers=franchise,
        json={"confirm_name": "权限测试主体", "reason": "无权越权操作"},
    )
    assert response.status_code == 403, response.text


def test_company_test_flag_migration_is_reversible() -> None:
    migration = Path("migrations/versions/0012_company_test_flag.py").read_text(
        encoding="utf-8"
    )

    assert 'revision = "0012_company_test_flag"' in migration
    assert 'down_revision = "0011_company_account_req"' in migration
    assert "op.add_column(" in migration
    assert '"companies"' in migration
    assert 'op.drop_column("companies", "is_test")' in migration
