from __future__ import annotations

from pathlib import Path

from ..core.enums import EvidenceType
from ..core.errors import AppError


_IMAGE_FORMATS = {
    "jpg": ({".jpg", ".jpeg"}, {"image/jpeg"}),
    "png": ({".png"}, {"image/png"}),
    "webp": ({".webp"}, {"image/webp"}),
}
_AUDIO_FORMATS = {
    "mp3": ({".mp3"}, {"audio/mpeg", "audio/mp3"}),
    "wav": ({".wav"}, {"audio/wav", "audio/x-wav"}),
    "m4a": ({".m4a"}, {"audio/mp4", "audio/x-m4a"}),
    "aac": ({".aac"}, {"audio/aac"}),
}
_CANONICAL_MIME = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
}


def _detect_format(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    if content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE6 == 0xE2):
        return "mp3"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE":
        return "wav"
    if len(content) >= 12 and content[4:8] == b"ftyp" and content[8:12] in {b"M4A ", b"isom", b"mp42"}:
        return "m4a"
    if len(content) >= 2 and content[0] == 0xFF and content[1] & 0xF6 == 0xF0:
        return "aac"
    return None


def validate_evidence_file(*, evidence_type: str, filename: str | None, mime_type: str | None, content: bytes) -> str:
    normalized_type = evidence_type.strip().upper()
    if not content:
        raise AppError("EVIDENCE_FILE_EMPTY", "证据文件不能为空", 422)
    detected = _detect_format(content)
    formats = _IMAGE_FORMATS if normalized_type == EvidenceType.CHAT_SCREENSHOT.value else _AUDIO_FORMATS if normalized_type == EvidenceType.CALL_RECORDING.value else None
    if formats is None:
        raise AppError("EVIDENCE_TYPE_INVALID", "证据类型无效", 422)
    if detected not in formats:
        raise AppError("EVIDENCE_FILE_SIGNATURE_INVALID", "证据文件签名与声明格式不一致", 422)
    extensions, mime_types = formats[detected]
    file_path = Path(filename or "")
    suffix = file_path.suffix.lower()
    normalized_mime = (mime_type or "").lower()
    if (
        len(file_path.suffixes) != 1
        or suffix not in extensions
        or (normalized_mime != "application/octet-stream" and normalized_mime not in mime_types)
    ):
        raise AppError("EVIDENCE_FILE_METADATA_INVALID", "证据文件扩展名、MIME 与文件签名必须一致", 422)
    return _CANONICAL_MIME[detected]
