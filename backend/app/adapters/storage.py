"""Object storage behind a small protocol: local disk (dev) or S3/MinIO."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def new_storage_key(prefix: str) -> str:
    # Random, never derived from user input or file names.
    return f"{prefix}/{secrets.token_hex(2)}/{secrets.token_hex(16)}"


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("storage key escapes the storage root")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self, endpoint_url: str, bucket: str, region: str, access_key: str, secret_key: str):
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "s3":
            _storage = S3Storage(s.s3_endpoint_url, s.s3_bucket, s.s3_region, s.s3_access_key, s.s3_secret_key)
        else:
            _storage = LocalStorage(s.storage_dir)
    return _storage


def set_storage(storage: ObjectStorage | None) -> None:
    global _storage
    _storage = storage
