from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import pathlib
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import boto3
import jwt
from botocore.config import Config
from jwt import InvalidTokenError

from ..core.config import get_settings
from ..core.errors import AppError
from ..core.security import ensure_canonical_jwt

settings = get_settings()
COS_CLIENT_CONFIG = Config(s3={"addressing_style": "virtual"})


def _validated_object_key(value: str) -> str:
    object_key = value.strip()
    parts = pathlib.PurePosixPath(object_key).parts
    if (
        not object_key
        or object_key.startswith("/")
        or "\\" in object_key
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise AppError("STORAGE_PATH_INVALID", "文件路径非法", 400)
    return object_key


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    size: int
    sha256: str
    mime_type: str


class ObjectStorage:
    def save(self, content: bytes, *, prefix: str, filename: str, mime_type: str) -> StoredObject:
        raise NotImplementedError

    def read(self, object_key: str) -> bytes:
        raise NotImplementedError

    def save_file(
        self,
        source: pathlib.Path,
        *,
        prefix: str,
        filename: str,
        mime_type: str,
        object_key: str | None = None,
        progress_callback: Callable[[], None] | None = None,
    ) -> StoredObject:
        raise NotImplementedError

    def iter_read(self, object_key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        raise NotImplementedError

    def delete(self, object_key: str) -> None:
        """Delete an object idempotently so durable cleanup jobs can retry safely."""

        raise NotImplementedError

    def check_readiness(self) -> None:
        """Verify the backend is reachable without writing an object."""

    def run_canary(self) -> str:
        """Exercise a disposable private object and return its non-sensitive key."""
        raise NotImplementedError


class LocalObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        self.root = pathlib.Path(settings.object_storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, *, prefix: str, filename: str, mime_type: str) -> StoredObject:
        suffix = pathlib.Path(filename).suffix.lower() or mimetypes.guess_extension(mime_type) or ".bin"
        object_key = f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"
        target = (self.root / object_key).resolve()
        if self.root not in target.parents:
            raise AppError("STORAGE_PATH_INVALID", "文件路径非法", 400)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredObject(object_key=object_key, size=len(content), sha256=hashlib.sha256(content).hexdigest(), mime_type=mime_type)

    def read(self, object_key: str) -> bytes:
        target = (self.root / object_key).resolve()
        if self.root not in target.parents or not target.exists():
            raise AppError("FILE_NOT_FOUND", "文件不存在", 404)
        return target.read_bytes()

    def save_file(
        self,
        source: pathlib.Path,
        *,
        prefix: str,
        filename: str,
        mime_type: str,
        object_key: str | None = None,
        progress_callback: Callable[[], None] | None = None,
    ) -> StoredObject:
        suffix = pathlib.Path(filename).suffix.lower() or mimetypes.guess_extension(mime_type) or ".bin"
        object_key = _validated_object_key(
            object_key or f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"
        )
        target = (self.root / object_key).resolve()
        if self.root not in target.parents:
            raise AppError("STORAGE_PATH_INVALID", "文件路径非法", 400)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.parent.chmod(0o700)
        digest = hashlib.sha256()
        size = 0
        try:
            with source.open("rb") as input_file, target.open("xb") as output_file:
                target.chmod(0o600)
                while chunk := input_file.read(1024 * 1024):
                    output_file.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                    if progress_callback is not None:
                        progress_callback()
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return StoredObject(
            object_key=object_key,
            size=size,
            sha256=digest.hexdigest(),
            mime_type=mime_type,
        )

    def iter_read(self, object_key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        target = (self.root / object_key).resolve()
        if self.root not in target.parents or not target.exists():
            raise AppError("FILE_NOT_FOUND", "文件不存在", 404)

        def chunks() -> Iterator[bytes]:
            with target.open("rb") as file:
                while chunk := file.read(chunk_size):
                    yield chunk

        return chunks()

    def delete(self, object_key: str) -> None:
        target = (self.root / object_key).resolve()
        if self.root not in target.parents:
            raise AppError("STORAGE_PATH_INVALID", "文件路径非法", 400)
        target.unlink(missing_ok=True)

    def check_readiness(self) -> None:
        if not self.root.is_dir() or not os.access(self.root, os.W_OK):
            raise AppError("STORAGE_NOT_READY", "对象存储目录不可写", 503)

    def run_canary(self) -> str:
        key = f".canary/zhongshu-readiness/{uuid.uuid4().hex}"
        target = (self.root / key).resolve()
        content = b"zhongshu-storage-canary-v1"
        created = False
        try:
            if self.root not in target.parents:
                raise AppError("STORAGE_PATH_INVALID", "文件路径非法", 400)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            created = True
            if target.read_bytes() != content:
                raise AppError("STORAGE_CANARY_INVALID", "对象存储 canary 内容校验失败", 503)
            return key
        except AppError:
            raise
        except OSError as exc:
            raise AppError("STORAGE_CANARY_FAILED", "对象存储 canary 失败", 503) from exc
        finally:
            if created:
                try:
                    target.unlink()
                except OSError as exc:
                    raise AppError("STORAGE_CANARY_CLEANUP_FAILED", "对象存储 canary 清理失败", 503) from exc


class S3ObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        endpoint_host = urlparse(settings.s3_endpoint_url).hostname
        client_options: dict[str, object] = {}
        if endpoint_host and endpoint_host.endswith(".myqcloud.com"):
            client_options["config"] = COS_CLIENT_CONFIG
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            region_name=settings.s3_region,
            **client_options,
        )

    def save(self, content: bytes, *, prefix: str, filename: str, mime_type: str) -> StoredObject:
        suffix = pathlib.Path(filename).suffix.lower() or mimetypes.guess_extension(mime_type) or ".bin"
        object_key = f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"
        digest = hashlib.sha256(content).hexdigest()
        self.client.put_object(Bucket=settings.s3_bucket, Key=object_key, Body=content, ContentType=mime_type, Metadata={"sha256": digest})
        return StoredObject(object_key=object_key, size=len(content), sha256=digest, mime_type=mime_type)

    def read(self, object_key: str) -> bytes:
        response = self.client.get_object(Bucket=settings.s3_bucket, Key=object_key)
        return response["Body"].read()

    def save_file(
        self,
        source: pathlib.Path,
        *,
        prefix: str,
        filename: str,
        mime_type: str,
        object_key: str | None = None,
        progress_callback: Callable[[], None] | None = None,
    ) -> StoredObject:
        suffix = pathlib.Path(filename).suffix.lower() or mimetypes.guess_extension(mime_type) or ".bin"
        object_key = _validated_object_key(
            object_key or f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"
        )
        digest = hashlib.sha256()
        with source.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
                if progress_callback is not None:
                    progress_callback()
        sha256 = digest.hexdigest()
        upload_options: dict[str, object] = {
            "ExtraArgs": {
                "ContentType": mime_type,
                "Metadata": {"sha256": sha256},
                "ServerSideEncryption": "AES256",
            },
        }
        if progress_callback is not None:
            upload_options["Callback"] = lambda _bytes_transferred: progress_callback()
        self.client.upload_file(
            str(source),
            settings.s3_bucket,
            object_key,
            **upload_options,
        )
        return StoredObject(
            object_key=object_key,
            size=source.stat().st_size,
            sha256=sha256,
            mime_type=mime_type,
        )

    def iter_read(self, object_key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        response = self.client.get_object(Bucket=settings.s3_bucket, Key=object_key)
        body = response["Body"]

        def chunks() -> Iterator[bytes]:
            try:
                while chunk := body.read(chunk_size):
                    yield chunk
            finally:
                body.close()

        return chunks()

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=settings.s3_bucket, Key=object_key)

    def check_readiness(self) -> None:
        try:
            self.client.head_bucket(Bucket=settings.s3_bucket)
        except Exception as exc:
            raise AppError("S3_NOT_READY", "对象存储 Bucket 不可达或权限不足", 503) from exc

    def run_canary(self) -> str:
        key = f".canary/zhongshu-readiness/{uuid.uuid4().hex}"
        content = b"zhongshu-storage-canary-v1"
        created = False
        try:
            self.client.put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=content,
                ContentType="application/octet-stream",
                Metadata={"purpose": "readiness-canary"},
            )
            created = True
            self.client.head_object(Bucket=settings.s3_bucket, Key=key)
            response = self.client.get_object(Bucket=settings.s3_bucket, Key=key)
            if response["Body"].read() != content:
                raise AppError("S3_CANARY_INVALID", "对象存储 canary 内容校验失败", 503)
            return key
        except AppError:
            raise
        except Exception as exc:
            raise AppError("S3_CANARY_FAILED", "对象存储 canary 失败", 503) from exc
        finally:
            if created:
                try:
                    self.client.delete_object(Bucket=settings.s3_bucket, Key=key)
                except Exception as exc:
                    raise AppError("S3_CANARY_CLEANUP_FAILED", "对象存储 canary 清理失败", 503) from exc


def get_storage() -> ObjectStorage:
    return S3ObjectStorage() if settings.object_storage_backend.lower() == "s3" else LocalObjectStorage()


def storage_target_snapshot() -> tuple[str, str]:
    backend = settings.object_storage_backend.strip().lower()
    if backend == "s3":
        parsed = urlparse(settings.s3_endpoint_url.strip())
        host = (parsed.hostname or "").lower()
        if parsed.port:
            host = f"{host}:{parsed.port}"
        endpoint = f"{parsed.scheme.lower()}://{host}{parsed.path.rstrip('/')}"
        namespace = json.dumps(
            {
                "bucket": settings.s3_bucket.strip(),
                "endpoint": endpoint,
                "region": settings.s3_region.strip(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return backend, namespace
    return "local", str(pathlib.Path(settings.object_storage_dir).resolve())


def create_file_access_token(evidence_id: str, user_id: str, expires_minutes: int = 10) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": evidence_id, "uid": user_id, "aud": "private-file", "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=expires_minutes)).timestamp())},
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_file_access_token(token: str) -> dict:
    try:
        ensure_canonical_jwt(token)
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience="private-file")
    except InvalidTokenError as exc:
        raise AppError("FILE_TOKEN_INVALID", "文件访问链接已失效", 403) from exc
