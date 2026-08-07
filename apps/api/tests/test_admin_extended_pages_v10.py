from __future__ import annotations


def login(client, username: str, password: str) -> dict[str, str]:
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['data']['token']}"}


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


def test_verification_task_can_be_assigned_and_reclaimed(api_client):
    client, _ = api_client
    admin = login(client, 'admin', 'Admin123!')
    users = data(client.get('/api/v1/admin-meta/telesales-users', headers=admin))
    telesales = users[0]
    tasks = data(client.get('/api/v1/verification/tasks?page=1&page_size=100', headers=admin))['items']
    task = next(item for item in tasks if item['status'] in {'PENDING', 'ASSIGNED'})

    data(client.post(f"/api/v1/verification/tasks/{task['id']}/assign", headers=admin, json={'assignee_user_id': telesales['id']}))
    assigned = data(client.get(f"/api/v1/verification/tasks/{task['id']}", headers=admin))
    assert assigned['status'] == 'ASSIGNED'
    assert assigned['assignee_user_id'] == telesales['id']

    data(client.post(f"/api/v1/verification/tasks/{task['id']}/reclaim", headers=admin))
    reclaimed = data(client.get(f"/api/v1/verification/tasks/{task['id']}", headers=admin))
    assert reclaimed['status'] == 'PENDING'
    assert reclaimed['assignee_user_id'] is None
