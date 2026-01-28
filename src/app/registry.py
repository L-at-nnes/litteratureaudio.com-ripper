"""
Thread-safe registries for tracking downloads and folder deduplication.

These classes keep track of what we've already processed to avoid:
- Downloading the same file twice
- Re-downloading audiobooks that appear in multiple places
"""

import threading
from pathlib import Path


class DownloadRegistry:
    """
    Keeps track of which files we've already downloaded in this session.
    
    The problem: When downloading a full author, the same MP3 might appear
    in multiple places (e.g., a track from a collective project AND the 
    same author's other works). We don't want to download it twice.
    
    Thread-safe because downloads happen in parallel.
    """
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.seen: set[str] = set()  # URLs we've already processed
        self.downloaded_paths: dict[str, Path] = {}  # URL -> where we saved it

    def allow(self, key: str) -> bool:
        """Check if we should download this URL. Returns False if already done."""
        if not key:
            return True
        with self.lock:
            if key in self.seen:
                return False
            self.seen.add(key)
            return True

    def register_download(self, key: str, path: Path) -> None:
        """Remember where we saved a file (for future reference)."""
        if not key:
            return
        with self.lock:
            self.downloaded_paths[key] = path

    def get_existing_path(self, key: str) -> Path | None:
        """Look up where we previously saved something."""
        with self.lock:
            return self.downloaded_paths.get(key)


class FolderRegistry:
    """
    Tracks which audiobook folders we've already downloaded.
    
    Used by --no-duplicates: if we're downloading Author X and then
    a collective project that includes the same book, we create a 
    shortcut instead of downloading again.
    
    Maps source_url -> local folder path.
    Thread-safe.
    """
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.downloaded: dict[str, Path] = {}

    def register(self, source_url: str, folder_path: Path) -> None:
        """Remember that we downloaded this URL to this folder."""
        with self.lock:
            self.downloaded[source_url] = folder_path

    def get_existing(self, source_url: str) -> Path | None:
        """Check if we already downloaded this URL. Returns the folder path or None."""
        with self.lock:
            return self.downloaded.get(source_url)
