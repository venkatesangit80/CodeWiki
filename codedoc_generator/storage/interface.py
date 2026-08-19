from abc import ABC, abstractmethod
from typing import List, Optional, Union

class BaseStorageProvider(ABC):
    @abstractmethod
    def read_file(self, path: str) -> Optional[str]:
        """
        Read text content from a file path or storage URL.
        
        Args:
            path: Local path or storage URL
            
        Returns:
            The content string, or None if reading failed
        """
        pass

    @abstractmethod
    def write_file(self, path: str, data: Union[str, bytes]) -> bool:
        """
        Write text or binary content to a file path or storage URL.
        
        Args:
            path: Local path or storage URL
            data: Content to write (string or raw bytes)
            
        Returns:
            True if the write succeeded, False otherwise
        """
        pass

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """
        Check if a file exists in storage.
        
        Args:
            path: Local path or storage URL
            
        Returns:
            True if it exists, False otherwise
        """
        pass

    @abstractmethod
    def list_files(self, prefix: str = "") -> List[str]:
        """
        List all file paths/keys in storage under a given prefix.
        
        Args:
            prefix: Key prefix to filter files
            
        Returns:
            A list of relative or absolute file paths/keys
        """
        pass
