import os
from typing import Dict, Any, Optional
from .interface import BaseStorageProvider
from .efs import EFSStorageProvider
from .s3 import S3StorageProvider
from .azure import AzureStorageProvider

def get_storage_provider(config: Any) -> BaseStorageProvider:
    """
    Get storage provider based on GeneratorConfig or dictionary configuration.
    Falls back to environment variables and EFS.
    """
    storage_type = "efs"
    conn_settings = {}
    
    if config:
        if isinstance(config, dict):
            storage_type = config.get("type", "efs").lower()
            conn_settings = config.get("connection_settings", {})
        else:
            # GeneratorConfig pydantic model
            storage_cfg = getattr(config, "storage", None)
            if storage_cfg:
                storage_type = getattr(storage_cfg, "type", "efs").lower()
                conn_settings = getattr(storage_cfg, "connection_settings", {})
                if hasattr(conn_settings, "model_dump"):
                    conn_settings = conn_settings.model_dump()
                elif not isinstance(conn_settings, dict):
                    conn_settings = {}
                    
    # Environment variable override
    storage_type = os.environ.get("STORAGE_TYPE", storage_type).lower()
    
    if storage_type == "s3":
        bucket_name = conn_settings.get("bucket_name") or os.environ.get("S3_BUCKET_NAME")
        region = conn_settings.get("region") or os.environ.get("AWS_REGION", "us-west-2")
        access_key = conn_settings.get("access_key") or os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = conn_settings.get("secret_key") or os.environ.get("AWS_SECRET_ACCESS_KEY")
        
        # Open Bao/Vault integration override
        try:
            from app.storage.vault_integration import is_vault_enabled, get_aws_credentials
            if is_vault_enabled():
                vault_creds = get_aws_credentials()
                if vault_creds:
                    access_key = vault_creds.get('access_key') or access_key
                    secret_key = vault_creds.get('secret_key') or secret_key
        except Exception:
            pass
            
        if not bucket_name:
            raise ValueError("S3 bucket_name is required when STORAGE_TYPE=s3")
        return S3StorageProvider(bucket_name, region, access_key, secret_key)
        
    elif storage_type == "azure":
        container_name = conn_settings.get("azure_container") or os.environ.get("AZURE_CONTAINER")
        connection_string = conn_settings.get("connection_string") or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        account_name = conn_settings.get("azure_account_name") or os.environ.get("AZURE_ACCOUNT_NAME")
        account_key = conn_settings.get("account_key") or os.environ.get("AZURE_STORAGE_KEY")
        
        # Open Bao/Vault integration override
        try:
            from app.storage.vault_integration import is_vault_enabled, get_azure_credentials
            if is_vault_enabled():
                vault_creds = get_azure_credentials()
                if vault_creds:
                    connection_string = vault_creds.get('connection_string') or connection_string
                    account_key = vault_creds.get('account_key') or account_key
        except Exception:
            pass
            
        if not container_name:
            raise ValueError("Azure container_name is required when STORAGE_TYPE=azure")
        return AzureStorageProvider(container_name, connection_string, account_name, account_key)
        
    else:
        base_path = conn_settings.get("base_path") or os.environ.get("EFS_BASE_PATH", ".")
        return EFSStorageProvider(base_path)
