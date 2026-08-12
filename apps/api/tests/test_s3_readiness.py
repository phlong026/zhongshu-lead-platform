from __future__ import annotations

import pytest

from apps.api.src.services import storage as storage_module
from apps.api.src.core.errors import AppError
from apps.api.src.services.storage import LocalObjectStorage, S3ObjectStorage


class _Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class _S3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.head_bucket_calls = 0

    def head_bucket(self, **_: str) -> None:
        self.head_bucket_calls += 1

    def put_object(self, *, Key: str, Body: bytes, **_: object) -> None:
        self.objects[Key] = Body

    def head_object(self, *, Key: str, **_: str) -> None:
        assert Key in self.objects

    def get_object(self, *, Key: str, **_: str) -> dict[str, _Body]:
        return {"Body": _Body(self.objects[Key])}

    def delete_object(self, *, Key: str, **_: str) -> None:
        del self.objects[Key]


def _storage(client: _S3Client) -> S3ObjectStorage:
    storage = object.__new__(S3ObjectStorage)
    storage.client = client
    return storage


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


def test_s3_readiness_hides_provider_error_details() -> None:
    class FailingClient(_S3Client):
        def head_bucket(self, **_: str) -> None:
            raise RuntimeError("access-key=should-not-appear")

    with pytest.raises(AppError, match="Bucket") as exc_info:
        _storage(FailingClient()).check_readiness()

    assert exc_info.value.code == "S3_NOT_READY"
    assert "should-not-appear" not in str(exc_info.value)
