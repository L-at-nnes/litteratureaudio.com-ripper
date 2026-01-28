"""
Constants and data classes used across the pipeline modules.

This file contains:
- ItemExtra: Keys for the item.extra dictionary (magic string constants)
- FolderPaths: Result of folder path calculations
- WP_API_BASE: WordPress API endpoint
"""

from dataclasses import dataclass
from pathlib import Path


# =============================================================================
# CONSTANTS - Keys used in item.extra dict
# =============================================================================
# These are the magic strings we use to pass context between iter_items and download_item.
# Using constants avoids typos and makes refactoring easier.

class ItemExtra:
    """Keys for the item.extra dictionary."""
    COLLECTION_ROOT = "collection_root"          # Name of the parent collection (e.g., "Le Comte de Monte-Cristo")
    GROUP_ROOT = "group_root"                    # Name of the author/reader/member listing
    AUTHOR_PREFIXED = "author_prefixed_collection"  # "Author - Project" folder name for direct collective projects
    SKIP_DOWNLOAD = "skip_download"              # True if this is a collection root (metadata only)
    LOOP_MORE_URL = "loop_more_url"              # URL for loading more tracks
    DURATION_MS = "duration_ms"                  # Duration in milliseconds from WP API
    WP_RAW_META = "wp_raw_meta"                  # Raw metadata from WordPress API


WP_API_BASE = "https://www.litteratureaudio.com/wp-json/wp/v2/posts"


@dataclass
class FolderPaths:
    """Result of determining where to save an item."""
    root_dir: Path          # The top-level output directory (or author folder)
    collection_dir: Path | None  # The collection folder (if any)
    item_dir: Path          # The final folder where files go
