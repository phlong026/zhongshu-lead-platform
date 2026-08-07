from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

settings = get_settings()
_password_hasher = PasswordHasher()
_fernet_key = base64.urlsafe_b64encode(hashlib.sha256(settings.field_encryption_key.encode("utf-8")).digest())
_fernet = Fernet(_fernet_key)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(subject: str, session_version: int, roles: list[str], company_id: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "sv": session_version,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    if company_id:
        payload["company_id"] = company_id
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def encrypt_text(value: str) -> str:
    return _fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet.decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None


def normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits


def _phone_hmac(value: str, secret: str) -> str:
    normalized = normalize_phone(value)
    return hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_phone(value: str) -> str:
    """Legacy compatible HMAC field used by V1.0.1 records."""

    return _phone_hmac(value, settings.phone_hash_secret)


def fingerprint_phone(value: str, *, secret: str | None = None) -> str:
    """Return the non-reversible V1.2 phone deduplication fingerprint."""

    return _phone_hmac(value, secret or settings.effective_phone_fingerprint_secret)


def mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_phone(value)
    if len(normalized) < 7:
        return "****"
    return normalized[:3] + "****" + normalized[-4:]


def generate_token(bytes_length: int = 32) -> str:
    return secrets.token_urlsafe(bytes_length)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_signed_state(payload: dict[str, Any], *, expires_minutes: int = 10, purpose: str = "state") -> str:
    now = datetime.now(timezone.utc)
    data = {
        **payload,
        "purpose": purpose,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(data, settings.jwt_secret, algorithm="HS256")


def decode_signed_state(token: str, *, purpose: str = "state") -> dict[str, Any]:
    data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if data.get("purpose") != purpose:
        raise jwt.InvalidTokenError("state purpose mismatch")
    return data
