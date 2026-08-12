from __future__ import annotations

import pytest

from apps.api.src.core.enums import EvidenceType
from apps.api.src.core.errors import AppError
from apps.api.src.services.evidence_file_validation import validate_evidence_file


@pytest.mark.parametrize(
    ("evidence_type", "filename", "mime_type", "content", "expected"),
    [
        (EvidenceType.CHAT_SCREENSHOT.value, "proof.png", "image/png", b"\x89PNG\r\n\x1a\nproof", "image/png"),
        (EvidenceType.CALL_RECORDING.value, "call.mp3", "application/octet-stream", b"ID3proof", "audio/mpeg"),
        (EvidenceType.CALL_RECORDING.value, "call.wav", "audio/wav", b"RIFFxxxxWAVEproof", "audio/wav"),
    ],
)
def test_accepts_matching_extension_mime_and_signature(evidence_type, filename, mime_type, content, expected):
    assert validate_evidence_file(evidence_type=evidence_type, filename=filename, mime_type=mime_type, content=content) == expected


@pytest.mark.parametrize(
    ("evidence_type", "filename", "mime_type", "content"),
    [
        (EvidenceType.CHAT_SCREENSHOT.value, "proof.jpg", "image/jpeg", b"not-an-image"),
        (EvidenceType.CHAT_SCREENSHOT.value, "proof.jpg.exe", "image/jpeg", b"\xff\xd8\xffproof"),
        (EvidenceType.CHAT_SCREENSHOT.value, "proof.jpg.png", "image/png", b"\x89PNG\r\n\x1a\nproof"),
        (EvidenceType.CALL_RECORDING.value, "call.mp3", "audio/mpeg", b""),
        (EvidenceType.CALL_RECORDING.value, "call.mp3", "audio/mpeg", b"\x89PNG\r\n\x1a\nproof"),
    ],
)
def test_rejects_forged_or_inconsistent_evidence(evidence_type, filename, mime_type, content):
    with pytest.raises(AppError):
        validate_evidence_file(evidence_type=evidence_type, filename=filename, mime_type=mime_type, content=content)
