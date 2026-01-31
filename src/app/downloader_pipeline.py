"""
Download logic: plan what to download, then download it.

This module handles:
- Building download plans (which files to get based on --format)
- Creating shortcuts for duplicates (--no-duplicates)
- The main download_item() orchestrator
- Helper functions for folder structure and metadata export
"""

import argparse
import logging
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from ..core.models import AudioItem, DownloadLink
from ..core.utils import ensure_dir, sanitize_filename, slug_from_url
from ..infra.downloader import (
    build_track_links,
    download_cover,
    download_file,
    resolve_link,
    tag_mp3,
    unzip_file,
)
from ..infra.http import RateLimiter, create_session
from ..report.export import export_description, export_json
from ..report.reporting import DryRunReporter, ProjectProgressTracker, SummaryCollector, item_display_label

from .constants import FolderPaths, ItemExtra
from .registry import DownloadRegistry, FolderRegistry


# =============================================================================
# DOWNLOAD PLAN BUILDING
# =============================================================================

def dedupe_links(links: list[DownloadLink]) -> list[DownloadLink]:
    """Remove duplicate download links based on filename or URL."""
    seen: set[str] = set()
    result = []
    for link in links:
        key = link.final_url or link.url
        if link.suggested_filename:
            key = f"file:{sanitize_filename(link.suggested_filename).lower()}"
        else:
            try:
                name = Path(urlparse(link.final_url or link.url).path).name
                if name:
                    key = f"file:{sanitize_filename(name).lower()}"
            except Exception:
                pass
        if key in seen:
            continue
        seen.add(key)
        result.append(link)
    return result


def build_download_plan(
    item: AudioItem,
    args: argparse.Namespace,
    session,
    rate_limiter: RateLimiter,
    logger: logging.Logger,
) -> tuple[list[DownloadLink], dict[str, str]]:
    """
    Decide which files to download based on --format option.
    
    Returns:
        (list of links to download, map of URL -> track title for ID3 tags)
    """
    raw_track_links = build_track_links(item.tracks)
    track_links = [resolve_link(session, link, rate_limiter, logger) for link in raw_track_links]
    track_title_map = {track.download_url: track.title for track in item.tracks if track.title}

    direct_mp3_links = [link for link in item.download_links if link.kind == "mp3"]
    pending_links = [link for link in item.download_links if link.kind != "mp3"]
    resolved_pending: list[DownloadLink] = []

    def resolve_pending() -> list[DownloadLink]:
        nonlocal resolved_pending
        if not resolved_pending:
            resolved_pending = [resolve_link(session, link, rate_limiter, logger) for link in pending_links]
        return resolved_pending

    all_mp3_links = track_links + direct_mp3_links
    if track_links:
        mp3_links = track_links
    elif direct_mp3_links:
        mp3_links = direct_mp3_links
    else:
        mp3_links = [link for link in resolve_pending() if link.kind == "mp3"]

    zip_links: list[DownloadLink] = []

    # Default policy: prefer MP3 tracks, fallback to ZIP when no MP3 is available.
    if args.format == "default":
        if mp3_links:
            plan = mp3_links
        else:
            zip_links = [link for link in resolve_pending() if link.kind == "zip"]
            plan = zip_links
    elif args.format == "mp3":
        if not mp3_links:
            logger.warning("No MP3 available for %s (only ZIP)", item.source_url)
            plan = []
        else:
            plan = mp3_links
    elif args.format == "zip":
        zip_links = [link for link in resolve_pending() if link.kind == "zip"]
        if not zip_links:
            logger.warning("No ZIP available for %s (only MP3)", item.source_url)
            plan = []
        else:
            plan = zip_links
    elif args.format == "mp3+zip":
        zip_links = [link for link in resolve_pending() if link.kind == "zip"]
        plan = mp3_links + zip_links
    elif args.format == "all":
        plan = all_mp3_links + resolve_pending()
    elif args.format == "unzip":
        zip_links = [link for link in resolve_pending() if link.kind == "zip"]
        plan = zip_links
        if not plan:
            logger.warning("No ZIP available for %s", item.source_url)
    else:
        plan = mp3_links

    return dedupe_links(plan), track_title_map


# =============================================================================
# SHORTCUT CREATION (for --no-duplicates)
# =============================================================================

def create_relative_shortcut(target_path: Path, shortcut_dir: Path, shortcut_name: str, logger: logging.Logger) -> bool:
    """
    Create a shortcut/redirect file to avoid re-downloading duplicates.
    
    Creates a .redirect.txt file with relative path information.
    This is portable across systems and doesn't require special permissions.
    
    Args:
        target_path: The folder that already exists (where the files are).
        shortcut_dir: The parent folder where the shortcut should be created.
        shortcut_name: The name for the shortcut entry.
        logger: For logging what we did.
    
    Returns:
        True if we created something, False if it already exists or failed.
    """
    try:
        shortcut_dir.mkdir(parents=True, exist_ok=True)
        
        # Calculate relative path
        try:
            rel_path = os.path.relpath(target_path, shortcut_dir)
        except ValueError:
            # Different drives on Windows - relative path impossible
            rel_path = str(target_path)
        
        # Create a redirect file with relative path
        redirect_file = shortcut_dir / f"{shortcut_name}.redirect.txt"
        if not redirect_file.exists():
            redirect_file.write_text(
                f"This album already exists elsewhere.\n"
                f"Relative path: {rel_path}\n",
                encoding="utf-8"
            )
            logger.info("Created redirect file to %s at %s", target_path.name, redirect_file)
            return True
        return False  # Already exists
    except Exception as exc:
        logger.warning("Failed to create shortcut to %s: %s", target_path, exc)
        return False


# =============================================================================
# FOLDER PATH DETERMINATION
# =============================================================================

def _build_versioned_item_name(item: AudioItem) -> str:
    """
    Build the folder name for an item, including version info if needed.
    
    Books with multiple versions (different readers) get distinct folder names:
    - "Nana" (original version, no suffix)
    - "Nana (Version 2 - René Depasse)" (version 2 with different reader)
    
    The version is detected from:
    1. URL containing "-version-N"
    2. Different readers for same title (handled at folder level)
    """
    from ..infra.parser import extract_version_from_url
    
    base_title = item.title or slug_from_url(item.source_url) or "work"
    base_name = sanitize_filename(base_title)
    
    # Check for version number in URL
    version_num = extract_version_from_url(item.source_url)
    
    if version_num:
        # URL indicates this is a versioned book
        reader_suffix = f" - {item.reader}" if item.reader else ""
        return f"{base_name} (Version {version_num}{reader_suffix})"
    
    return base_name


def _determine_folder_paths(
    item: AudioItem,
    item_name: str,
    output_dir: Path,
) -> FolderPaths:
    """
    Figure out the correct folder structure for an item.
    
    This is the complex logic that decides where files go based on:
    - Is this from an author listing? -> Author/Book/
    - Is this a collective project? -> Author - Project/ or Project/
    - Is this a single album? -> Author - Title/
    - Is this a nested project? -> Parent/NestedProject/Book/
    
    Returns a FolderPaths object with root_dir, collection_dir, and item_dir.
    """
    collection_root = item.extra.get(ItemExtra.COLLECTION_ROOT)
    group_root = item.extra.get(ItemExtra.GROUP_ROOT)
    author_prefixed = item.extra.get(ItemExtra.AUTHOR_PREFIXED)
    skip_download = item.extra.get(ItemExtra.SKIP_DOWNLOAD)
    
    # Case 1: Single album at root (not from author download, not from collection)
    is_single_album_at_root = (
        not collection_root
        and not group_root
        and item.author
        and not skip_download
    )
    
    collection_dir = None
    
    if author_prefixed:
        # This item belongs to an author-prefixed collection
        parent_dir = output_dir / sanitize_filename(str(author_prefixed))
        
        # Extract the project name from "Author - Project" format
        parent_project_name = author_prefixed.split(" - ", 1)[-1] if " - " in author_prefixed else author_prefixed
        
        # Check if this is a nested project or child of one
        is_nested = collection_root and collection_root != parent_project_name
        
        if skip_download and is_nested:
            # This is the ROOT of a NESTED project (e.g., "La Vallée de la peur" inside "Sherlock Holmes")
            collection_dir = parent_dir / sanitize_filename(str(collection_root))
            item_dir = collection_dir
        elif skip_download:
            # This is the root of the main author-prefixed collection itself
            item_dir = parent_dir
            collection_dir = item_dir
        elif is_nested:
            # This is a CHILD of a nested project (e.g., "Épisode 1" of "La Vallée de la peur")
            nested_dir = parent_dir / sanitize_filename(str(collection_root))
            collection_dir = nested_dir
            item_dir = nested_dir / item_name
        else:
            # This is a regular child book in the main collection
            collection_dir = parent_dir
            item_dir = collection_dir / item_name
        root_dir = output_dir
        
    elif is_single_album_at_root:
        # Single album: "Author - Title" at root
        folder_name = f"{sanitize_filename(item.author)} - {item_name}"
        item_dir = output_dir / folder_name
        root_dir = output_dir
        
    elif group_root:
        # From author/reader/member listing: "Author/Book/" or "Author/Project/Book/"
        root_dir = output_dir / sanitize_filename(str(group_root))
        if collection_root:
            collection_dir = root_dir / sanitize_filename(str(collection_root))
            item_dir = collection_dir if skip_download else collection_dir / item_name
        else:
            item_dir = root_dir / item_name
            
    else:
        # Direct collection URL without author: "Project/Book/"
        root_dir = output_dir
        if collection_root:
            collection_dir = root_dir / sanitize_filename(str(collection_root))
            item_dir = collection_dir if skip_download else collection_dir / item_name
        else:
            item_dir = root_dir / item_name
    
    return FolderPaths(root_dir=root_dir, collection_dir=collection_dir, item_dir=item_dir)


# =============================================================================
# DOWNLOAD HELPERS
# =============================================================================

def _files_exist_on_disk(
    item_dir: Path,
    item: AudioItem,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> bool:
    """
    Check if audio files for this item already exist on disk.
    
    Used by --no-duplicates to skip re-downloading existing files.
    Returns True if the folder exists and contains MP3 or ZIP files.
    """
    if not item_dir.exists():
        return False
    
    # Check for audio files
    audio_extensions = {'.mp3', '.zip', '.m4a', '.ogg'}
    audio_files = [f for f in item_dir.iterdir() if f.is_file() and f.suffix.lower() in audio_extensions]
    
    if audio_files:
        logger.debug("Found %d existing audio files in %s", len(audio_files), item_dir)
        return True
    
    return False


def _handle_duplicate_shortcut(
    item: AudioItem,
    item_dir: Path,
    folder_registry: FolderRegistry,
    summary: SummaryCollector | None,
    project_tracker: ProjectProgressTracker | None,
    logger: logging.Logger,
) -> bool:
    """
    Check if this item already exists and create a shortcut if so.
    
    Returns True if a shortcut was created (skip normal download), False otherwise.
    """
    existing_path = folder_registry.get_existing(item.source_url)
    if not existing_path or not existing_path.exists():
        return False
    
    # Create shortcut instead of downloading
    parent_dir = item_dir.parent
    shortcut_name = item_dir.name
    create_relative_shortcut(existing_path, parent_dir, shortcut_name, logger)
    
    if summary:
        summary.add_item(item, item_dir, downloaded_files=[])
    
    collection_root = item.extra.get(ItemExtra.COLLECTION_ROOT)
    if project_tracker and collection_root:
        project_tracker.mark_done(collection_root, item.title or item_dir.name, logger)
    
    return True


def _handle_dry_run(
    item: AudioItem,
    item_dir: Path,
    args: argparse.Namespace,
    session,
    rate_limiter: RateLimiter,
    logger: logging.Logger,
    reporter: DryRunReporter | None,
    summary: SummaryCollector | None,
    project_tracker: ProjectProgressTracker | None,
) -> None:
    """Handle --dry-run mode: log what would happen without downloading."""
    label = item_display_label(item)
    skip_download = item.extra.get(ItemExtra.SKIP_DOWNLOAD)
    collection_root = item.extra.get(ItemExtra.COLLECTION_ROOT)
    
    if skip_download:
        child_count = len(item.collection_urls)
        message = f"COLLECTION: {label} | items={child_count} | output={item_dir} | url={item.source_url}"
        logger.info("DRY-RUN: %s -> metadata only into %s (items: %s)", label, item_dir, child_count)
        if reporter:
            reporter.write(message)
        if summary:
            summary.add_item(item, item_dir, planned_count=0)
    else:
        plan, _ = build_download_plan(item, args, session, rate_limiter, logger)
        message = f"DRY-RUN: {label} | files={len(plan)} | output={item_dir} | url={item.source_url}"
        logger.info("DRY-RUN: %s -> %s file(s) into %s", label, len(plan), item_dir)
        if reporter:
            reporter.write(message)
        if summary:
            summary.add_item(item, item_dir, planned_count=len(plan))
        if project_tracker and collection_root:
            project_tracker.mark_done(collection_root, item.title or item_dir.name, logger)


def _export_metadata(
    item: AudioItem,
    item_name: str,
    item_dir: Path,
    args: argparse.Namespace,
    logger: logging.Logger,
    downloaded_files: list[Path] | None = None,
) -> None:
    """Export description.txt and JSON metadata."""
    if not args.no_description:
        desc_path = item_dir / "description.txt"
        export_description(item.description_text, desc_path)
        if desc_path.exists():
            from ..core.utils import format_size
            logger.info("Created description.txt (%s)", format_size(desc_path.stat().st_size, "kb"))
    if not args.no_json:
        json_path = item_dir / f"{item_name}.json"
        export_json(item, json_path, downloaded_files or [])
        if json_path.exists():
            from ..core.utils import format_size
            logger.info("Created %s (%s)", json_path.name, format_size(json_path.stat().st_size, "kb"))


def _download_audio_files(
    item: AudioItem,
    item_dir: Path,
    args: argparse.Namespace,
    session,
    rate_limiter: RateLimiter,
    registry: DownloadRegistry,
    logger: logging.Logger,
    cover_path: Path | None,
) -> list[Path]:
    """Download all audio files for an item."""
    plan, track_title_map = build_download_plan(item, args, session, rate_limiter, logger)
    
    if not plan:
        logger.info("No downloads for %s (%s)", item_display_label(item), item.source_url)
        return []
    
    downloaded_files: list[Path] = []
    for link in plan:
        key = link.final_url or link.url
        if not registry.allow(key):
            logger.debug("Skipping duplicate %s", key)
            continue
        
        path = download_file(
            session,
            link.final_url or link.url,
            item_dir,
            rate_limiter,
            logger,
            suggested_filename=link.suggested_filename,
        )
        if not path:
            continue
        
        downloaded_files.append(path)
        
        # Tag MP3 files with metadata
        if path.suffix.lower() == ".mp3" and not args.no_id3:
            track_title = track_title_map.get(link.url)
            tag_mp3(path, item, cover_path, track_title, logger)
        
        # Unzip if requested
        if args.format == "unzip" and path.suffix.lower() == ".zip":
            unzip_dir = item_dir / "unzipped"
            ensure_dir(unzip_dir)
            unzip_file(path, unzip_dir, logger)
    
    return downloaded_files


# =============================================================================
# MAIN DOWNLOAD FUNCTION
# =============================================================================

def download_item(
    item: AudioItem,
    args: argparse.Namespace,
    output_dir: Path,
    rate_limiter: RateLimiter,
    registry: DownloadRegistry,
    logger: logging.Logger,
    reporter: DryRunReporter | None = None,
    summary: SummaryCollector | None = None,
    project_tracker: ProjectProgressTracker | None = None,
    folder_registry: FolderRegistry | None = None,
) -> list[Path]:
    """
    Download a single audiobook (or just its metadata).
    
    This is the main orchestrator that delegates to sub-functions:
    - _determine_folder_paths(): figure out where to save
    - _handle_duplicate_shortcut(): create shortcut if --no-duplicates
    - _handle_dry_run(): log what would happen if --dry-run
    - _export_metadata(): save description.txt and JSON
    - _download_audio_files(): download the actual audio
    
    Returns the list of downloaded file paths.
    """
    session = create_session()
    # Use versioned name if URL indicates a version (e.g., "-version-2")
    item_name = _build_versioned_item_name(item)
    
    # Step 1: Determine folder structure
    paths = _determine_folder_paths(item, item_name, output_dir)
    skip_download = item.extra.get(ItemExtra.SKIP_DOWNLOAD)
    collection_root = item.extra.get(ItemExtra.COLLECTION_ROOT)
    item_dir = paths.item_dir

    # Step 2: Check for duplicates (--no-duplicates mode)
    # This checks if files already exist on disk before downloading
    if getattr(args, 'no_duplicates', False) and not skip_download:
        if _files_exist_on_disk(item_dir, item, args, logger):
            logger.info("Skipping %s - files already exist at %s", item.title or item.source_url, item_dir)
            if summary:
                summary.add_item(item, item_dir, downloaded_files=[])
            if project_tracker and collection_root:
                project_tracker.mark_done(collection_root, item.title or item_dir.name, logger)
            return []

    # Step 3: Handle dry-run mode
    if args.dry_run:
        _handle_dry_run(item, item_dir, args, session, rate_limiter, logger, reporter, summary, project_tracker)
        return []

    # Step 4: Create directories
    ensure_dir(paths.root_dir)
    if paths.collection_dir:
        ensure_dir(paths.collection_dir)
    ensure_dir(item_dir)

    # Step 5: Download cover
    cover_path = None
    if item.cover_url and not args.no_cover:
        cover_path = download_cover(session, item.cover_url, item_dir, rate_limiter, logger)

    # Step 6a: Metadata-only mode (--metadata-only)
    if args.metadata_only:
        _export_metadata(item, item_name, item_dir, args, logger, downloaded_files=[])
        if summary:
            summary.add_item(item, item_dir, downloaded_files=[])
        if project_tracker and collection_root:
            project_tracker.mark_done(collection_root, item.title or item_dir.name, logger)
        if folder_registry:
            folder_registry.register(item.source_url, item_dir)
        return []

    # Step 6b: Collection root (skip_download=True) - just metadata
    if skip_download:
        _export_metadata(item, item_name, item_dir, args, logger, downloaded_files=[])
        if summary:
            summary.add_item(item, item_dir, downloaded_files=[])
        return []

    # Step 7: Download audio files
    downloaded_files = _download_audio_files(
        item, item_dir, args, session, rate_limiter, registry, logger, cover_path
    )

    # Step 8: Export metadata with downloaded files list
    _export_metadata(item, item_name, item_dir, args, logger, downloaded_files)

    # Step 9: Update trackers
    if summary:
        summary.add_item(item, item_dir, downloaded_files=downloaded_files)
    if project_tracker and collection_root:
        project_tracker.mark_done(collection_root, item.title or item_dir.name, logger)
    if folder_registry:
        folder_registry.register(item.source_url, item_dir)

    return downloaded_files
