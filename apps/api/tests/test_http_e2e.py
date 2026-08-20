from __future__ import annotations

from sqlalchemy import select

from apps.api.src.core.models import Assignment, AuditLog, PointsAccount, PointsLedger, ReturnRequest


def _login(client, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.cookies.get("access_token")
    assert token
    assert "token" not in response.json()["data"]
    return {"Authorization": f"Bearer {token}"}


def _data(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["request_id"]
    return payload["data"]


def test_role_aware_dashboard_and_candidate_projection(api_client):
    client, _ = api_client
    operation = _login(client, "operation", "Operation123!")
    owner = _login(client, "owner", "Owner123!")

    operation_summary = _data(client.get("/api/v1/dashboard/summary", headers=operation))
    assert "business" in operation_summary
    assert "finance" not in operation_summary

    owner_summary = _data(client.get("/api/v1/dashboard/summary", headers=owner))
    assert owner_summary["finance"]["points_balance_total"] > 0

    qualified = _data(client.get("/api/v1/dispatch/qualified-leads", headers=operation))
    lead = next(item for item in qualified["items"] if item["customer_name"] == "王女士")
    candidates = _data(client.get(f"/api/v1/dispatch/leads/{lead['id']}/candidates", headers=operation))
    eligible = next(item for item in candidates if item["eligible"])
    assert eligible["eligibility_label"] == "可派"
    assert "points_balance" not in eligible
    assert "available_points" not in eligible


def test_full_http_dispatch_claim_followup_return_refund(api_client):
    client, factory = api_client
    operation = _login(client, "operation", "Operation123!")
    franchise = _login(client, "franchise_demo", "Franchise123!")
    reviewer = _login(client, "reviewer", "Reviewer123!")
    admin = _login(client, "admin", "Admin123!")

    qualified = _data(client.get("/api/v1/dispatch/qualified-leads", headers=operation))
    lead = next(item for item in qualified["items"] if item["customer_name"] == "王女士")
    candidates = _data(client.get(f"/api/v1/dispatch/leads/{lead['id']}/candidates", headers=operation))
    company = next(item for item in candidates if item["eligible"])
    company_id = company["company_id"]

    before_account = _data(client.get(f"/api/v1/points/accounts/{company_id}", headers=franchise))
    before_balance = before_account["balance"]

    assignment = _data(
        client.post(
            f"/api/v1/dispatch/leads/{lead['id']}",
            headers=operation,
            json={
                "company_id": company_id,
                "idempotency_key": "http-e2e-dispatch-001",
                "reason": "HTTP 全链路验收",
            },
        )
    )
    assignment_id = assignment["id"]
    assert assignment["status"] == "PENDING_CLAIM"

    masked_detail = _data(client.get(f"/api/v1/claims/assignments/{assignment_id}", headers=franchise))
    assert masked_detail["lead"]["phone"] is None
    assert masked_detail["lead"]["phone_masked"].endswith("0003")
    assert masked_detail["lead"]["contact_unlocked"] is False

    claim_result = _data(
        client.post(
            f"/api/v1/claims/assignments/{assignment_id}",
            headers=franchise,
            json={"idempotency_key": "http-e2e-claim-001"},
        )
    )
    assert claim_result["assignment"]["status"] == "CLAIMED"
    assert claim_result["assignment"]["lead"]["phone"] == "13800000003"
    assert claim_result["ledger"]["delta"] == -assignment["points_price"]

    after_claim = _data(client.get(f"/api/v1/points/accounts/{company_id}", headers=franchise))
    assert after_claim["balance"] == before_balance - assignment["points_price"]

    followup = _data(
        client.post(
            f"/api/v1/followups/assignments/{assignment_id}",
            headers=franchise,
            json={"status": "CONTACTED", "note": "已电话联系，客户反馈号码信息异常。"},
        )
    )
    assert followup["status"] == "CONTACTED"

    return_request = _data(
        client.post(
            f"/api/v1/returns/assignments/{assignment_id}/draft",
            headers=franchise,
            json={"reason_code": "INFO_ERROR", "description": "客户确认关键信息与提交内容不一致。"},
        )
    )
    return_id = return_request["id"]
    assert return_request["status"] == "DRAFT"

    screenshot = client.post(
        f"/api/v1/returns/{return_id}/evidence",
        headers=franchise,
        data={"evidence_type": "CHAT_SCREENSHOT"},
        files={"file": ("chat.png", b"\x89PNG\r\n\x1a\nmock-chat", "image/png")},
    )
    assert _data(screenshot)["type"] == "CHAT_SCREENSHOT"

    recording = client.post(
        f"/api/v1/returns/{return_id}/evidence",
        headers=franchise,
        data={"evidence_type": "CALL_RECORDING", "duration_seconds": "38"},
        files={"file": ("call.mp3", b"ID3mock-audio", "audio/mpeg")},
    )
    assert _data(recording)["type"] == "CALL_RECORDING"

    submitted = _data(client.post(f"/api/v1/returns/{return_id}/submit", headers=franchise))
    assert submitted["status"] == "PENDING"
    assert {item["type"] for item in submitted["evidences"]} == {"CHAT_SCREENSHOT", "CALL_RECORDING"}

    reviewed = _data(
        client.post(
            f"/api/v1/returns/{return_id}/review",
            headers=reviewer,
            json={"decision": "APPROVE", "note": "截图与录音证据完整，审核通过。"},
        )
    )
    assert reviewed["status"] == "APPROVED"
    assert reviewed["refund_points"] == assignment["points_price"]

    after_refund = _data(client.get(f"/api/v1/points/accounts/{company_id}", headers=franchise))
    assert after_refund["balance"] == before_balance

    with factory() as db:
        assignment_row = db.get(Assignment, assignment_id)
        return_row = db.get(ReturnRequest, return_id)
        account = db.scalar(select(PointsAccount).where(PointsAccount.company_id == company_id))
        assignment_ledgers = db.scalars(
            select(PointsLedger).where(
                PointsLedger.company_id == company_id,
                PointsLedger.business_type == "ASSIGNMENT",
                PointsLedger.business_id == assignment_id,
            )
        ).all()
        refund_ledger = db.scalar(
            select(PointsLedger).where(
                PointsLedger.company_id == company_id,
                PointsLedger.business_type == "RETURN_REQUEST",
                PointsLedger.business_id == return_id,
            )
        )
        assert assignment_row.status == "RETURNED"
        assert return_row.status == "APPROVED"
        assert account.balance == before_balance
        assert [item.delta for item in assignment_ledgers] == [-assignment["points_price"]]
        assert refund_ledger.delta == assignment["points_price"]
        assert refund_ledger.related_ledger_id == assignment_ledgers[0].id

    audits = _data(client.get("/api/v1/audit-logs?page_size=200", headers=admin))
    actions = {item["action"] for item in audits["items"]}
    assert {
        "LEAD_DISPATCH",
        "ASSIGNMENT_CLAIM",
        "FOLLOWUP_CREATE",
        "RETURN_SUBMIT",
        "RETURN_REVIEW",
    }.issubset(actions)
    with factory() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "RETURN_REVIEW")) is not None


def test_static_entrypoints_are_served(api_client):
    client, _ = api_client
    for path, marker in [
        ("/h5/", "合家美宅"),
        ("/call/", "电销"),
        ("/admin/", "合家美宅"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert marker in response.text
