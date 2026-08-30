from __future__ import annotations

from io import BytesIO
from pathlib import Path
import stat

import pytest

from apps.api.src.services import storage as storage_module
from apps.api.src.core.errors import AppError
from apps.api.src.services.storage import LocalObjectStorage, S3ObjectStorage


class _Body:
    def __init__(self, content: bytes) -> None:
        self.content = BytesIO(content)

    def read(self, size: int = -1) -> bytes:
        return self.content.read(size)

    def close(self) -> None:
        self.content.close()


class _S3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.head_bucket_calls = 0
        self.upload_extra_args: dict[str, object] = {}

    def head_bucket(self, **_: str) -> None:
        self.head_bucket_calls += 1

    def put_object(self, *, Key: str, Body: bytes, **_: object) -> None:
        self.objects[Key] = Body

    def head_object(self, *, Key: str, **_: str) -> None:
        assert Key in self.objects

    def get_object(self, *, Key: str, **_: str) -> dict[str, _Body]:
        return {"Body": _Body(self.objects[Key])}

    def delete_object(self, *, Key: str, **_: str) -> None:
        self.objects.pop(Key, None)

    def upload_file(
        self,
        filename: str,
        _bucket: str,
        key: str,
        *,
        ExtraArgs: dict[str, object],
        Callback=None,
    ) -> None:
        content = Path(filename).read_bytes()
        self.objects[key] = content
        self.upload_extra_args = ExtraArgs
        if Callback is not None:
            Callback(len(content))


def _storage(client: _S3Client) -> S3ObjectStorage:
    storage = object.__new__(S3ObjectStorage)
    storage.client = client
    return storage


def test_s3_client_uses_virtual_hosted_style_for_tencent_cos(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(service_name: str, **kwargs: object) -> _S3Client:
        captured["service_name"] = service_name
        captured.update(kwargs)
        return _S3Client()

    monkeypatch.setattr(storage_module.boto3, "client", fake_client)
    monkeypatch.setattr(storage_module.settings, "s3_endpoint_url", "https://cos.ap-shanghai.myqcloud.com")
    monkeypatch.setattr(storage_module.settings, "s3_access_key_id", "cos-secret-id")
    monkeypatch.setattr(storage_module.settings, "s3_secret_access_key", "cos-secret-key")
    monkeypatch.setattr(storage_module.settings, "s3_region", "ap-shanghai")

    S3ObjectStorage()

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "https://cos.ap-shanghai.myqcloud.com"
    assert captured["region_name"] == "ap-shanghai"
    assert captured["config"].s3 == {"addressing_style": "virtual"}


def test_s3_client_keeps_default_addressing_for_non_cos_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(service_name: str, **kwargs: object) -> _S3Client:
        captured["service_name"] = service_name
        captured.update(kwargs)
        return _S3Client()

    monkeypatch.setattr(storage_module.boto3, "client", fake_client)
    monkeypatch.setattr(storage_module.settings, "s3_endpoint_url", "https://s3.example.com")

    S3ObjectStorage()

    assert captured["service_name"] == "s3"
    assert "config" not in captured


def test_s3_readiness_only_checks_bucket_without_writing() -> None:
    client = _S3Client()

    _storage(client).check_readiness()

    assert client.head_bucket_calls == 1
    assert client.objects == {}


def test_local_canary_reads_then_deletes_disposable_object(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    root = tmp_path / "private-storage"
    monkeypatch.setattr(storage_module.settings, "object_storage_dir", str(root))

    key = LocalObjectStorage().run_canary()

    assert key.startswith(".canary/zhongshu-readiness/")
    assert list(root.rglob("*")) == [root / ".canary", root / ".canary" / "zhongshu-readiness"]


def test_s3_canary_reads_then_deletes_disposable_object() -> None:
    client = _S3Client()

    key = _storage(client).run_canary()

    assert key.startswith(".canary/zhongshu-readiness/")
    assert client.objects == {}


def test_storage_delete_is_idempotent_for_local_and_s3(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    root = tmp_path / "private-storage"
    monkeypatch.setattr(storage_module.settings, "object_storage_dir", str(root))
    local = LocalObjectStorage()
    stored = local.save(
        b"cleanup",
        prefix="returns/test",
        filename="evidence.bin",
        mime_type="application/octet-stream",
    )

    local.delete(stored.object_key)
    local.delete(stored.object_key)

    client = _S3Client()
    client.objects["returns/test/evidence.bin"] = b"cleanup"
    s3 = _storage(client)
    s3.delete("returns/test/evidence.bin")
    s3.delete("returns/test/evidence.bin")
    assert client.objects == {}


def test_local_save_file_is_private_and_reads_in_chunks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    root = tmp_path / "private-storage"
    source = tmp_path / "sensitive.zip"
    source.write_bytes(b"complete-phone-export")
    monkeypatch.setattr(storage_module.settings, "object_storage_dir", str(root))

    local = LocalObjectStorage()
    stored = local.save_file(
        source,
        prefix="lead-exports/test",
        filename="export.zip",
        mime_type="application/zip",
    )

    target = root / stored.object_key
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert b"".join(local.iter_read(stored.object_key, chunk_size=3)) == source.read_bytes()


def test_local_save_file_reports_copy_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    root = tmp_path / "private-storage"
    source = tmp_path / "sensitive.zip"
    source.write_bytes(b"complete-phone-export")
    monkeypatch.setattr(storage_module.settings, "object_storage_dir", str(root))
    progress_events: list[bool] = []

    LocalObjectStorage().save_file(
        source,
        prefix="lead-exports/test",
        filename="export.zip",
        mime_type="application/zip",
        progress_callback=lambda: progress_events.append(True),
    )

    assert progress_events


def test_s3_save_file_requests_server_side_encryption(tmp_path) -> None:
    source = tmp_path / "sensitive.zip"
    source.write_bytes(b"complete-phone-export")
    client = _S3Client()

    stored = _storage(client).save_file(
        source,
        prefix="lead-exports/test",
        filename="export.zip",
        mime_type="application/zip",
    )

    assert client.objects[stored.object_key] == source.read_bytes()
    assert client.upload_extra_args["ServerSideEncryption"] == "AES256"
    assert client.upload_extra_args["ContentType"] == "application/zip"


def test_s3_save_file_reports_upload_progress(tmp_path) -> None:
    source = tmp_path / "sensitive.zip"
    source.write_bytes(b"complete-phone-export")
    progress_events: list[bool] = []

    _storage(_S3Client()).save_file(
        source,
        prefix="lead-exports/test",
        filename="export.zip",
        mime_type="application/zip",
        progress_callback=lambda: progress_events.append(True),
    )

    assert progress_events


def test_s3_cleanup_target_changes_when_endpoint_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage_module.settings, "object_storage_backend", "s3")
    monkeypatch.setattr(storage_module.settings, "s3_bucket", "same-bucket")
    monkeypatch.setattr(storage_module.settings, "s3_region", "ap-shanghai")
    monkeypatch.setattr(storage_module.settings, "s3_endpoint_url", "https://old.example.com/")
    old_target = storage_module.storage_target_snapshot()

    monkeypatch.setattr(storage_module.settings, "s3_endpoint_url", "https://new.example.com")
    new_target = storage_module.storage_target_snapshot()

    assert old_target != new_target
    assert "old.example.com" in old_target[1]
    assert "new.example.com" in new_target[1]


def test_s3_readiness_hides_provider_error_details() -> None:
    class FailingClient(_S3Client):
        def head_bucket(self, **_: str) -> None:
            raise RuntimeError("access-key=should-not-appear")

    with pytest.raises(AppError, match="Bucket") as exc_info:
        _storage(FailingClient()).check_readiness()

    assert exc_info.value.code == "S3_NOT_READY"
    assert "should-not-appear" not in str(exc_info.value)
