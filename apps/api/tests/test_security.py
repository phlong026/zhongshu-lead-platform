from apps.api.src.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_text,
    encrypt_text,
    hash_phone,
    mask_phone,
    normalize_phone,
)


def test_phone_security_roundtrip() -> None:
    phone = "138-0013-8000"
    assert normalize_phone(phone) == "13800138000"
    assert mask_phone(phone) == "138****8000"
    assert hash_phone(phone) == hash_phone("+86 13800138000")
    assert decrypt_text(encrypt_text(phone)) == phone


def test_jwt_roundtrip() -> None:
    token = create_access_token("user-1", 2, ["SUPER_ADMIN"], "company-1")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["sv"] == 2
    assert payload["company_id"] == "company-1"
