"""File storage abstraction — local disk or optional AWS S3."""

import logging
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self):
        self.settings = get_settings()
        self._s3 = None

    def _get_s3_client(self):
        if self._s3 is not None:
            return self._s3
        try:
            import boto3

            self._s3 = boto3.client(
                "s3",
                region_name=self.settings.aws_region,
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
            )
        except ImportError:
            logger.warning("boto3 not installed; S3 storage unavailable")
        return self._s3

    def _s3_key(self, relative_path: str) -> str:
        prefix = self.settings.s3_prefix.strip("/")
        rel = relative_path.replace("\\", "/").lstrip("/")
        return f"{prefix}/{rel}" if prefix else rel

    def save_bytes(self, data: bytes, relative_path: str) -> str:
        if self.settings.storage_backend == "s3" and self.settings.s3_bucket:
            client = self._get_s3_client()
            if client:
                key = self._s3_key(relative_path)
                client.put_object(Bucket=self.settings.s3_bucket, Key=key, Body=data)
                return f"s3://{self.settings.s3_bucket}/{key}"
        dest = self.settings.upload_dir / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return str(dest.resolve())

    def save_upload_file(self, content: bytes, subdir: str, filename: str) -> Path:
        rel = f"{subdir}/{filename}"
        path_str = self.save_bytes(content, rel)
        if path_str.startswith("s3://"):
            local = self.settings.upload_dir / rel
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(content)
            return local
        return Path(path_str)

    def resolve_local_path(self, stored_path: str) -> Path:
        return Path(stored_path)
