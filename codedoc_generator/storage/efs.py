import os
from typing import List, Optional, Union
from .interface import BaseStorageProvider

class EFSStorageProvider(BaseStorageProvider):
    def __init__(self, base_path: str = "."):
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)

    def _resolve_path(self, path: str) -> str:
        if path.startswith("file://"):
            path = path[len("file://"):]
        if os.path.isabs(path):
            return os.path.abspath(path)
        return os.path.abspath(os.path.join(self.base_path, path))

    def read_file(self, path: str) -> Optional[str]:
        full_path = self._resolve_path(path)
        if not os.path.exists(full_path):
            return None
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    def write_file(self, path: str, data: Union[str, bytes]) -> bool:
        full_path = self._resolve_path(path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            if isinstance(data, bytes):
                with open(full_path, "wb") as f:
                    f.write(data)
            else:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(data)
            return True
        except Exception:
            return False

    def file_exists(self, path: str) -> bool:
        full_path = self._resolve_path(path)
        return os.path.exists(full_path) and os.path.isfile(full_path)

    def list_files(self, prefix: str = "") -> List[str]:
        full_prefix_path = self._resolve_path(prefix)
        if os.path.isfile(full_prefix_path):
            return [os.path.relpath(full_prefix_path, self.base_path)]
        if not os.path.exists(full_prefix_path):
            return []
            
        files = []
        for root, _, filenames in os.walk(full_prefix_path):
            for f in filenames:
                if f.startswith("."):
                    continue
                full_path = os.path.join(root, f)
                rel = os.path.relpath(full_path, self.base_path)
                files.append(rel)
        return files
