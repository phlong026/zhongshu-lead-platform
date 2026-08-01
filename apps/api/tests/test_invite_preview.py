from apps.api.src.schemas.company import CompanyCreateBody
from apps.api.src.services.auth_service import create_company_invite
from apps.api.src.services.company_service import create_company


def test_invite_preview_returns_only_safe_company_summary(api_client) -> None:
    client, factory = api_client
    with factory() as session:
        company = create_company(
            session,
            CompanyCreateBody(
                code="SH-PREVIEW",
                name="上海预览加盟商",
                owner_name="李老板",
                region_codes=["310100"],
                capabilities=[{"category_code": "VILLA_DECORATION", "brand_code": "ZHONGSHU"}],
            ),
        )
        _, token = create_company_invite(session, company.id, None, 24)
        session.commit()
    response = client.get("/api/v1/auth/invites/preview", params={"invite": token})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["company_name"] == "上海预览加盟商"
    assert data["owner_name"] == "李老板"
    assert data["region_codes"] == ["310100"]
    assert data["capability_codes"] == ["VILLA_DECORATION"]
    assert "contact_phone" not in data
    assert "points" not in data
