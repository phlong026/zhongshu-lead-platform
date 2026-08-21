from pathlib import Path

path = Path('apps/api/src/services/invite_binding_service.py')
text = path.read_text(encoding='utf-8')

prefix_old = '''    user_id = uuid_str()
    occupied = db.execute(
'''
prefix_new = '''    user_id = uuid_str()
    # PostgreSQL enforces the primary_user_id foreign key immediately. Create
    # the candidate user inside the same transaction before occupying the
    # company row; any conflict or later failure rolls the candidate back.
    user = User(
        id=user_id,
        display_name=nickname or company.owner_name or "微信加盟商",
        company_id=company.id,
        status="ACTIVE",
        last_login_at=utcnow(),
    )
    db.add(user)
    db.flush()

    occupied = db.execute(
'''
if prefix_old in text:
    text = text.replace(prefix_old, prefix_new, 1)

old_after = '''    if company.primary_user_id != user_id:
        raise AppError("AUTH_COMPANY_BIND_CONFLICT", "公司主账号占用结果异常", 409)

    user = User(
        id=user_id,
        display_name=nickname or company.owner_name or "微信加盟商",
        company_id=company.id,
        status="ACTIVE",
        last_login_at=utcnow(),
    )
    db.add(user)
    db.flush()
    assign_role(db, user, "FRANCHISE_OWNER")
'''
new_after = '''    if company.primary_user_id != user_id:
        raise AppError("AUTH_COMPANY_BIND_CONFLICT", "公司主账号占用结果异常", 409)

    assign_role(db, user, "FRANCHISE_OWNER")
'''
if old_after in text:
    text = text.replace(old_after, new_after, 1)

if text.count('user = User(\n        id=user_id,') != 1:
    raise RuntimeError('candidate user creation must appear exactly once')
if 'db.refresh(company, attribute_names=["primary_user_id"])' not in text:
    raise RuntimeError('primary user identity-map refresh missing')
path.write_text(text, encoding='utf-8')
