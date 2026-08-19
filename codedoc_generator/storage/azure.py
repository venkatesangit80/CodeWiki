import logging
import re
from typing import List, Optional, Union
from urllib.parse import urlparse
from .interface import BaseStorageProvider

logger = logging.getLogger(__name__)

class AzureStorageProvider(BaseStorageProvider):
    def __init__(self, container_name: str, connection_string: Optional[str] = None, account_name: Optional[str] = None, account_key: Optional[str] = None):
        self.container_name = container_name
        self.blob_service_client = None
        try:
            from azure.storage.blob import BlobServiceClient
            if connection_string:
                self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
                logger.info("Azure Storage initialized via Connection String")
            elif account_name and account_key:
                account_url = f"https://{account_name}.blob.core.windows.net"
                self.blob_service_client = BlobServiceClient(account_url=account_url, credential=account_key)
                logger.info("Azure Storage initialized via Account Key")
            else:
                logger.error("Azure credentials not provided")
        except Exception as e:
            logger.error(f"Failed to initialize Azure Blob client: {e}")

    def _parse_url(self, path: str) -> str:
        if path.startswith("azure://") or path.startswith("wasb://") or path.startswith("wasbs://"):
            parsed = urlparse(path)
            return parsed.path.lstrip("/")
        # format: https://account.blob.core.windows.net/container/blob
        match = re.match(r'https://[^.]+\.blob\.core\.windows\.net/[^/]+/(.+)', path)
        if match:
            return match.group(1)
        return path.lstrip("/")

    def read_file(self, path: str) -> Optional[str]:
        if not self.blob_service_client:
            return None
        blob_name = self._parse_url(path)
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            blob_client = container_client.get_blob_client(blob_name)
            return blob_client.download_blob().readall().decode("utf-8")
        except Exception as e:
            logger.debug(f"Failed to read from Azure Blob: {e}")
            return None

    def write_file(self, path: str, data: Union[str, bytes]) -> bool:
        if not self.blob_service_client:
            return False
        blob_name = self._parse_url(path)
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            try:
                container_client.create_container()
            except Exception:
                pass
            blob_client = container_client.get_blob_client(blob_name)
            body_data = data if isinstance(data, bytes) else data.encode("utf-8")
            blob_client.upload_blob(body_data, overwrite=True)
            return True
        except Exception as e:
            logger.error(f"Failed to write to Azure Blob: {e}")
            return False

    def file_exists(self, path: str) -> bool:
        if not self.blob_service_client:
            return False
        blob_name = self._parse_url(path)
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.get_blob_properties()
            return True
        except Exception:
            return False

    def list_files(self, prefix: str = "") -> List[str]:
        if not self.blob_service_client:
            return []
        prefix = self._parse_url(prefix)
        try:
            container_client = self.blob_service_client.get_container_client(self.container_name)
            blobs = container_client.list_blobs(name_starts_with=prefix)
            return [blob.name for blob in blobs]
        except Exception as e:
            logger.error(f"Failed to list Azure blobs: {e}")
            return []
