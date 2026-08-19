import logging
from typing import List, Optional, Union
from urllib.parse import urlparse
from .interface import BaseStorageProvider

logger = logging.getLogger(__name__)

class S3StorageProvider(BaseStorageProvider):
    def __init__(self, bucket_name: str, region: str = "us-west-2", access_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = None
        try:
            import boto3
            client_kwargs = {"region_name": region}
            if access_key and secret_key:
                client_kwargs["aws_access_key_id"] = access_key
                client_kwargs["aws_secret_access_key"] = secret_key
            self.s3_client = boto3.client("s3", **client_kwargs)
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")

    def _parse_url(self, path: str) -> str:
        if path.startswith("s3://"):
            parsed = urlparse(path)
            return parsed.path.lstrip("/")
        return path.lstrip("/")

    def read_file(self, path: str) -> Optional[str]:
        if not self.s3_client:
            logger.error("S3 client not initialized")
            return None
        key = self._parse_url(path)
        try:
            resp = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return resp["Body"].read().decode("utf-8")
        except Exception as e:
            logger.debug(f"Failed to read from S3: {e}")
            return None

    def write_file(self, path: str, data: Union[str, bytes]) -> bool:
        if not self.s3_client:
            logger.error("S3 client not initialized")
            return False
        key = self._parse_url(path)
        try:
            body_data = data if isinstance(data, bytes) else data.encode("utf-8")
            self.s3_client.put_object(Bucket=self.bucket_name, Key=key, Body=body_data)
            return True
        except Exception as e:
            logger.error(f"Failed to write to S3: {e}")
            return False

    def file_exists(self, path: str) -> bool:
        if not self.s3_client:
            return False
        key = self._parse_url(path)
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False

    def list_files(self, prefix: str = "") -> List[str]:
        if not self.s3_client:
            return []
        prefix = self._parse_url(prefix)
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            files = []
            for page in pages:
                for obj in page.get("Contents", []):
                    files.append(obj["Key"])
            return files
        except Exception as e:
            logger.error(f"Failed to list files from S3: {e}")
            return []
