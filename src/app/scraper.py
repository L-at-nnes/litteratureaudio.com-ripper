"""
Scraping logic: crawl URLs and extract AudioItems.

This module handles:
- Page type detection and routing
- Listing pagination (authors, readers, members)
- Collective project handling
- WordPress API enrichment
- Track list loading ("voir plus")
"""

import argparse
import logging
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..core.models import AudioItem, DownloadLink
from ..core.utils import sanitize_filename, slug_from_url
from ..infra.http import RateLimiter, fetch_html, fetch_json
from ..infra.parser import (
    detect_page_type,
    extract_listing_name,
    extract_listing_urls,
    extract_loop_more_url,
    extract_track_items,
    find_next_page,
    make_soup,
    parse_work_page,
)
from ..report.reporting import ProjectProgressTracker, item_display_label

from .constants import ItemExtra, WP_API_BASE


def normalize_url(url: str) -> str:
    """Remove URL fragment for consistent comparison."""
    parts = urlsplit(url)
    parts = parts._replace(fragment="")
    return urlunsplit(parts)


def strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    soup = BeautifulSoup(text or "", "html.parser")
    return soup.get_text(strip=True)


def format_duration_ms(ms: int | None) -> str | None:
    """Convert milliseconds to HH:MM:SS or MM:SS format."""
    if ms is None:
        return None
    try:
        total = int(ms) // 1000
    except Exception:
        return None
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def enrich_with_wp_api(
    item: AudioItem,
    session,
    rate_limiter: RateLimiter,
    logger: logging.Logger,
) -> None:
    """
    Fetch extra metadata from WordPress REST API.
    
    The site exposes a WP JSON API that has:
    - Better title/description (rendered HTML)
    - Cover image URL
    - Duration in milliseconds
    - Direct download/stream URLs
    
    Retries up to 3 times if the API call fails.
    """
    if not item.post_id:
        return
    
    api_url = f"{WP_API_BASE}/{item.post_id}?_embed=1"
    data = None
    max_attempts = 3
    
    for attempt in range(1, max_attempts + 1):
        try:
            if attempt > 1:
                logger.debug("Retry WP API (%s/%s) for post %s", attempt, max_attempts, item.post_id)
            data = fetch_json(session, api_url, rate_limiter)
            break  # Success, exit retry loop
        except Exception as exc:
            if attempt < max_attempts:
                logger.debug("WP API failed, will retry (%s/%s) for %s: %s", attempt, max_attempts, item.post_id, exc)
                time.sleep(attempt * 0.5)  # Short delay for API calls
                continue
            logger.debug("WP API failed after %s attempts for %s: %s", max_attempts, item.post_id, exc)
            return
    
    if not data:
        return

    if not item.title:
        title = data.get("title", {}).get("rendered")
        if title:
            item.title = strip_html(title)

    if not item.description_text:
        excerpt = data.get("excerpt", {}).get("rendered")
        if excerpt:
            item.description_text = strip_html(excerpt)

    embedded = data.get("_embedded", {})
    media = embedded.get("wp:featuredmedia") or []
    if not item.cover_url and media:
        item.cover_url = media[0].get("source_url")

    meta = data.get("meta", {})
    if meta:
        duration_ms = meta.get("duration")
        item.extra[ItemExtra.DURATION_MS] = duration_ms
        if not item.duration:
            item.duration = format_duration_ms(duration_ms)

        download_url = meta.get("download_url")
        stream_url = meta.get("stream") or meta.get("stream_url")
        for url in [download_url, stream_url]:
            if url:
                kind = "mp3" if str(url).lower().endswith(".mp3") else "unknown"
                link = DownloadLink(url=str(url), kind=kind)
                if not any(existing.url == link.url for existing in item.download_links):
                    item.download_links.append(link)

    item.extra[ItemExtra.WP_RAW_META] = meta


def load_more_tracks(
    item: AudioItem,
    soup: BeautifulSoup,
    session,
    rate_limiter: RateLimiter,
    logger: logging.Logger,
) -> None:
    """
    Load additional tracks from paginated "voir plus" button.
    
    Track lists are paginated behind a "scroller" link (10 items per page).
    This function follows those links until there are no more.
    """
    loop_url = item.extra.get(ItemExtra.LOOP_MORE_URL) or extract_loop_more_url(soup)
    if not loop_url:
        return

    seen_tracks = {track.download_url for track in item.tracks}
    seen_pages: set[str] = set()
    page_count = 0

    while loop_url and loop_url not in seen_pages:
        seen_pages.add(loop_url)
        page_count += 1
        try:
            data = fetch_json(session, loop_url, rate_limiter)
        except Exception as exc:
            logger.warning("Loop-more fetch failed for %s: %s", loop_url, exc)
            break

        content = data.get("content") if isinstance(data, dict) else None
        if not content:
            break

        loop_soup = make_soup(content)
        new_tracks = extract_track_items(loop_soup, item.source_url)
        added = 0
        for track in new_tracks:
            if track.download_url in seen_tracks:
                continue
            seen_tracks.add(track.download_url)
            item.tracks.append(track)
            added += 1

        loop_url = extract_loop_more_url(loop_soup)
        if added == 0 and not loop_url:
            break

    if page_count:
        logger.info(
            "Loop-more: %s extra page(s) for %s (tracks: %s)",
            page_count,
            item_display_label(item),
            len(item.tracks),
        )


def iter_items(
    start_urls: list[str],
    session,
    rate_limiter: RateLimiter,
    args: argparse.Namespace,
    logger: logging.Logger,
    project_tracker: ProjectProgressTracker | None = None,
):
    """
    The heart of the scraper: crawls URLs and yields AudioItems to download.
    
    This is a generator that handles three types of pages:
    
    1. LISTING PAGES (author/voice/member):
       - Extracts all work URLs from the listing
       - Follows pagination (page 2, page 3...)
       - Adds works to the queue with group_root set (so they end up in Author/Book/)
    
    2. COLLECTIVE PROJECTS (e.g., "Le Comte de Monte-Cristo Œuvre intégrale"):
       - These are pages that link to multiple child books
       - We yield the project itself (metadata only, skip_download=True)
       - Then add all child URLs to the queue
       - Children get collection_root set so they end up in Project/Book/
    
    3. REGULAR WORKS:
       - Parse the page, enrich with WordPress API data
       - Load any extra tracks (the "voir plus" button loads 10 at a time)
       - Yield the item for download
    
    The maps (collection_map, group_map, author_prefixed_map) track which 
    folder structure each URL should use when downloaded.
    """
    queue = deque(start_urls)
    seen: set[str] = set()  # URLs we've already processed
    collection_map: dict[str, str] = {}  # child_url -> collection name (for nested projects)
    group_map: dict[str, str] = {}  # child_url -> author/reader name (for listings)
    author_prefixed_map: dict[str, str] = {}  # child_url -> "Author - Project" folder name

    while queue:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        try:
            html = fetch_html(session, url, rate_limiter)
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", url, exc)
            continue

        page_type = detect_page_type(url, html)

        if page_type in ["author_listing", "voice_listing", "member_listing"]:
            current_url = url
            page_count = 0
            group_name = None
            while current_url:
                page_count += 1
                soup = make_soup(html)
                if group_name is None:
                    group_name = extract_listing_name(soup, page_type)
                group_root = sanitize_filename(group_name or slug_from_url(current_url) or "listing")
                for work_url in extract_listing_urls(soup, current_url):
                    normalized_work = normalize_url(work_url)
                    group_map[normalized_work] = group_root
                    if normalized_work not in seen:
                        queue.append(normalized_work)
                # Follow pagination for listing pages (authors, readers, members).
                next_page = find_next_page(soup)
                if next_page:
                    next_page = urlunsplit(urlsplit(urljoin(current_url, next_page)))
                if not next_page or (args.max_pages and page_count >= args.max_pages):
                    break
                current_url = next_page
                if current_url in seen:
                    break
                try:
                    html = fetch_html(session, current_url, rate_limiter)
                except Exception as exc:
                    logger.warning("Failed to fetch page %s: %s", current_url, exc)
                    break
            continue

        if page_type in ["work", "track", "unknown"]:
            item, soup = parse_work_page(url, html)
            if args.no_description:
                item.description_text = None
            enrich_with_wp_api(item, session, rate_limiter, logger)
            load_more_tracks(item, soup, session, rate_limiter, logger)
            if item.tracks:
                item.is_collective_project = True
            collection_root = collection_map.get(normalize_url(item.source_url))
            if collection_root:
                item.extra[ItemExtra.COLLECTION_ROOT] = collection_root
            group_root = group_map.get(normalize_url(item.source_url))
            if group_root:
                item.extra[ItemExtra.GROUP_ROOT] = group_root
            
            # Check if this child belongs to an author-prefixed collection
            author_prefixed = author_prefixed_map.get(normalize_url(item.source_url))
            if author_prefixed:
                item.extra[ItemExtra.AUTHOR_PREFIXED] = author_prefixed

            if item.collection_urls:
                root_name = sanitize_filename(item.title or slug_from_url(item.source_url) or "collection")
                if project_tracker:
                    project_tracker.register(root_name, len(item.collection_urls), logger)
                    
                # Special case: "Auteurs divers" collective projects should ALWAYS be independent,
                # even if found from an author listing. They go in their own folder at root.
                is_multi_author_collective = (
                    item.is_collective_project
                    and item.author
                    and item.author.lower() == "auteurs divers"
                )
                
                # For collective projects with a single author (not from group listing),
                # we'll use "Author - Project" folder format at root.
                # BUT: if we already have an author_prefixed from a parent project,
                # we're a nested project and should stay inside the parent.
                is_collective_single_author = (
                    item.is_collective_project
                    and item.author
                    and not group_root  # Not coming from an author/voice listing
                    and not author_prefixed  # Not already nested inside another project
                )
                child_author_prefixed = None
                child_group_root = group_root  # May be overridden for multi-author collectives
                
                if is_multi_author_collective:
                    # Multi-author collective: gets its own folder "Auteurs divers - Project" at root
                    # This overrides any parent group_root - children go to independent folder
                    child_author_prefixed = f"Auteurs divers - {root_name}"
                    item.extra[ItemExtra.AUTHOR_PREFIXED] = child_author_prefixed
                    # Clear group_root so children DON'T inherit the original author's folder
                    child_group_root = None  # Critical: clears inheritance for children
                    # Also clear from item itself
                    item.extra.pop(ItemExtra.GROUP_ROOT, None)
                elif is_collective_single_author:
                    child_author_prefixed = f"{sanitize_filename(item.author)} - {root_name}"
                    item.extra[ItemExtra.AUTHOR_PREFIXED] = child_author_prefixed
                elif author_prefixed:
                    # We're a nested project - keep parent's author_prefixed for children
                    child_author_prefixed = author_prefixed
                    
                for child_url in item.collection_urls:
                    normalized_child = normalize_url(child_url)
                    collection_map[normalized_child] = root_name
                    if child_group_root:
                        group_map[normalized_child] = child_group_root
                    if child_author_prefixed:
                        author_prefixed_map[normalized_child] = child_author_prefixed
                    if normalized_child not in seen:
                        queue.append(normalized_child)
                # Collection root: metadata only.
                item.extra[ItemExtra.COLLECTION_ROOT] = root_name
                item.extra[ItemExtra.SKIP_DOWNLOAD] = True
                yield item
                continue
            yield item
            continue
