import os
import hashlib
import json
import logging
from typing import Dict, List, Set, Tuple
from git import Repo

logger = logging.getLogger(__name__)

class IngestionEngine:
    def __init__(self, repo_id: str, local_path: str, ignore_paths: List[str], state_dir: str):
        self.repo_id = repo_id
        self.local_path = os.path.abspath(local_path)
        self.ignore_paths = ignore_paths
        self.state_dir = state_dir
        self.state_file = os.path.join(state_dir, f"state_{repo_id.replace('/', '__')}.json")
        os.makedirs(state_dir, exist_ok=True)
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, str]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading state file: {e}")
        return {}

    def save_state(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state file: {e}")

    def _should_ignore(self, path: str) -> bool:
        # Calculate relative path from local_path
        rel_path = os.path.relpath(path, self.local_path)
        parts = rel_path.split(os.sep)
        for ignore in self.ignore_paths:
            if ignore in parts or rel_path.startswith(ignore):
                return True
        return False

    def calculate_file_hash(self, filepath: str) -> str:
        sha256 = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error reading file {filepath} for hashing: {e}")
            return ""

    def scan_repository(self) -> Tuple[List[str], List[str], List[str]]:
        """
        Scan repository files and detect changes using file hashes.
        Returns:
            Tuple of (new_files, changed_files, deleted_files) relative paths.
        """
        current_files: Dict[str, str] = {}
        new_files: List[str] = []
        changed_files: List[str] = []
        deleted_files: List[str] = []

        # Find all files on disk
        for root, dirs, files in os.walk(self.local_path):
            # Prune ignored directories in-place to avoid walking them
            dirs[:] = [d for d in dirs if not self._should_ignore(os.path.join(root, d))]
            
            for file in files:
                filepath = os.path.join(root, file)
                if self._should_ignore(filepath):
                    continue
                
                # Check binary files by checking extensions or content
                if self._is_binary_file(filepath):
                    continue

                rel_path = os.path.relpath(filepath, self.local_path)
                file_hash = self.calculate_file_hash(filepath)
                if file_hash:
                    current_files[rel_path] = file_hash

        # Detect new or changed
        for rel_path, file_hash in current_files.items():
            if rel_path not in self.state:
                new_files.append(rel_path)
            elif self.state[rel_path] != file_hash:
                changed_files.append(rel_path)

        # Detect deleted
        for rel_path in self.state.keys():
            if rel_path not in current_files:
                deleted_files.append(rel_path)

        # Update temporary state, but let analyzer process them first before committing
        # We store current_files as the candidate state
        self.candidate_state = current_files

        return new_files, changed_files, deleted_files

    def commit_state(self):
        """Commit the scanned state as the official persistent state."""
        if hasattr(self, "candidate_state"):
            self.state = self.candidate_state
            self.save_state()

    def _is_binary_file(self, filepath: str) -> bool:
        # Check standard binary file extensions
        binary_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz",
            ".mp4", ".mp3", ".wav", ".avi", ".mov", ".db", ".sqlite", ".pyc", ".pyd",
            ".so", ".dll", ".exe", ".bin", ".woff", ".woff2", ".ttf", ".eot", ".docx",
            ".xlsx", ".pptx", ".DS_Store"
        }
        ext = os.path.splitext(filepath)[1].lower()
        if ext in binary_extensions:
            return True

        # Fallback check first 1024 bytes for null character
        try:
            with open(filepath, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" in chunk
        except Exception:
            return True
