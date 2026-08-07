from apps.api.src.services.audit import sanitize_audit_value


def test_audit_sanitizer_redacts_plaintext_phone_and_secrets() -> None:
    value = sanitize_audit_value(
        {
            "phone": "13800138000",
            "phone_masked": "138****8000",
            "nested": {
                "contact_phone_encrypted": "ciphertext",
                "access_token": "token-value",
                "ordinary": "kept",
            },
        }
    )
    assert value["phone"] == "[REDACTED]"
    assert value["phone_masked"] == "138****8000"
    assert value["nested"]["contact_phone_encrypted"] == "[REDACTED]"
    assert value["nested"]["access_token"] == "[REDACTED]"
    assert value["nested"]["ordinary"] == "kept"
