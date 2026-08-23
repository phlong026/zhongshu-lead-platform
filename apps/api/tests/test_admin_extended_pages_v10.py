from __future__ import annotations


def login(client, username: str, password: str) -> dict[str, str]:
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200, response.text
    token = response.cookies.get('access_token')
    assert token
    assert 'token' not in response.json()['data']
    return {'Authorization': f'Bearer {token}'}


def data(response):
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['code'] == 'OK'
    return payload['data']


def test_admin_meta_rbac_and_company_detail(api_client):
    client, _ = api_client
    admin = login(client, 'admin', 'Admin123!')
    operation = login(client, 'operation', 'Operation123!')

    matrix = data(client.get('/api/v1/admin-meta/rbac-matrix', headers=admin))
    assert any(role['code'] == 'SUPER_ADMIN' for role in matrix)
    assert any(permission['sensitive'] for role in matrix for permission in role['permissions'])
    denied = client.get('/api/v1/admin-meta/rbac-matrix', headers=operation)
    assert denied.status_code == 403

    telesales_users = data(client.get('/api/v1/admin-meta/telesales-users', headers=operation))
    assert telesales_users
    assert all(item['status'] == 'ACTIVE' for item in telesales_users)
    assert all(set(item) == {'id', 'display_name', 'username', 'status'} for item in telesales_users)

    companies = data(client.get('/api/v1/companies?page=1&page_size=20', headers=admin))['items']
    detail = data(client.get(f"/api/v1/admin-meta/companies/{companies[0]['id']}", headers=admin))
    assert detail['id'] == companies[0]['id']
    assert 'members' in detail
    assert 'contact_phone_masked' in detail
    assert 'contact_phone' not in detail


def test_legacy_verification_assignment_writes_stay_disabled(api_client, monkeypatch):
    client, _ = api_client
    import apps.api.src.core.legacy_guard as legacy_guard

    monkeypatch.setattr(legacy_guard.settings, 'legacy_write_enabled', False)
    admin = login(client, 'admin', 'Admin123!')
    tasks = data(client.get('/api/v1/verification/tasks?page=1&page_size=100', headers=admin))['items']
    task = next(item for item in tasks if item['status'] in {'PENDING', 'ASSIGNED'})
    before = data(client.get(f"/api/v1/verification/tasks/{task['id']}", headers=admin))

    assign = client.post(
        f"/api/v1/verification/tasks/{task['id']}/assign",
        headers=admin,
        json={'assignee_user_id': 'legacy-write-must-stay-disabled'},
    )
    assert assign.status_code == 410
    assert assign.json()['code'] == 'LEGACY_WRITE_DISABLED'

    reclaim = client.post(f"/api/v1/verification/tasks/{task['id']}/reclaim", headers=admin)
    assert reclaim.status_code == 410
    assert reclaim.json()['code'] == 'LEGACY_WRITE_DISABLED'

    after = data(client.get(f"/api/v1/verification/tasks/{task['id']}", headers=admin))
    assert after['status'] == before['status']
    assert after['assignee_user_id'] == before['assignee_user_id']
