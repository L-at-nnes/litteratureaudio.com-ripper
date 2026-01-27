import argparse
import logging
import threading
from collections import deque
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

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
from ..infra.http import RateLimiter, create_session, fetch_html, fetch_json
from ..report.export import export_description, export_json
from ..report.reporting import DryRunReporter, ProjectProgressTracker, SummaryCollector, item_display_label
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


WP_API_BASE = "https://www.litteratureaudio.com/wp-json/wp/v2/posts"


class DownloadRegistry:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.seen = set()

    def allow(self, key: str) -> bool:
        if not key:
            return True
        with self.lock:
            if key in self.seen:
                return False
            self.seen.add(key)
            return True


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    parts = parts._replace(fragment="")
    return urlunsplit(parts)


def strip_html(text: str) -> str:
    soup = BeautifulSoup(text or "", "html.parser")
    return soup.get_text(strip=True)


def format_duration_ms(ms: int | None) -> str | None:
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
    if not item.post_id:
        return
    api_url = f"{WP_API_BASE}/{item.post_id}?_embed=1"
    try:
        data = fetch_json(session, api_url, rate_limiter)
    except Exception as exc:
        logger.debug("WP API failed for %s: %s", item.post_id, exc)
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
        item.extra["duration_ms"] = duration_ms
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

    item.extra["wp_raw_meta"] = meta


def load_more_tracks(
    item: AudioItem,
    soup: BeautifulSoup,
    session,
    rate_limiter: RateLimiter,
    logger: logging.Logger,
) -> None:
    # Track lists are paginated behind a "scroller" link (10 items per page).
    loop_url = item.extra.get("loop_more_url") or extract_loop_more_url(soup)
    if not loop_url:
        return

    seen_tracks = {track.download_url for track in item.tracks}
    seen_pages = set()
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
    queue = deque(start_urls)
    seen = set()
    collection_map: dict[str, str] = {}
    group_map: dict[str, str] = {}

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
                item.extra["collection_root"] = collection_root
            group_root = group_map.get(normalize_url(item.source_url))
            if group_root:
                item.extra["group_root"] = group_root

            if item.collection_urls:
                root_name = sanitize_filename(item.title or slug_from_url(item.source_url) or "collection")
                if project_tracker:
                    project_tracker.register(root_name, len(item.collection_urls), logger)
                for child_url in item.collection_urls:
                    normalized_child = normalize_url(child_url)
                    collection_map[normalized_child] = root_name
                    if group_root:
                        group_map[normalized_child] = group_root
                    if normalized_child not in seen:
                        queue.append(normalized_child)
                # Collection root: metadata only.
                item.extra["collection_root"] = root_name
                item.extra["skip_download"] = True
                yield item
                continue
            yield item
            continue


def dedupe_links(links: list[DownloadLink]) -> list[DownloadLink]:
    seen = set()
    result = []
    for link in links:
        key = link.final_url or link.url
        if link.suggested_filename:
            key = f"file:{sanitize_filename(link.suggested_filename).lower()}"
        else:
            try:
                from urllib.parse import urlparse

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
) -> list[Path]:
    session = create_session()
    item_name = sanitize_filename(item.title or slug_from_url(item.source_url) or "work")
    collection_root = item.extra.get("collection_root")
    group_root = item.extra.get("group_root")
    if group_root:
        root_dir = output_dir / sanitize_filename(str(group_root))
    else:
        root_dir = output_dir

    if collection_root:
        collection_dir = root_dir / sanitize_filename(str(collection_root))
        if item.extra.get("skip_download"):
            item_dir = collection_dir
        else:
            item_dir = collection_dir / item_name
    else:
        item_dir = root_dir / item_name

    if args.dry_run:
        label = item_display_label(item)
        if item.extra.get("skip_download"):
            child_count = len(item.collection_urls)
            message = f"COLLECTION: {label} | items={child_count} | output={item_dir} | url={item.source_url}"
            logger.info("DRY-RUN: %s -> metadata only into %s (items: %s)", label, item_dir, child_count)
            if reporter:
                reporter.write(message)
            if summary:
                summary.add_item(item, item_dir, planned_count=0)
            return []

        plan, _ = build_download_plan(item, args, session, rate_limiter, logger)
        message = f"DRY-RUN: {label} | files={len(plan)} | output={item_dir} | url={item.source_url}"
        logger.info("DRY-RUN: %s -> %s file(s) into %s", label, len(plan), item_dir)
        if reporter:
            reporter.write(message)
        if summary:
            summary.add_item(item, item_dir, planned_count=len(plan))
        if project_tracker and item.extra.get("collection_root"):
            project_tracker.mark_done(item.extra.get("collection_root"), item.title or item_dir.name, logger)
        return []

    ensure_dir(root_dir)
    if collection_root:
        ensure_dir(collection_dir)
    ensure_dir(item_dir)

    cover_path = None
    if item.cover_url and not args.no_cover:
        cover_path = download_cover(session, item.cover_url, item_dir, rate_limiter, logger)

    if args.metadata_only:
        if not args.no_description:
            export_description(item.description_text, item_dir / "description.txt")
        if not args.no_json:
            export_json(item, item_dir / f"{item_name}.json", [])
        if summary:
            summary.add_item(item, item_dir, downloaded_files=[])
        if project_tracker and item.extra.get("collection_root"):
            project_tracker.mark_done(item.extra.get("collection_root"), item.title or item_dir.name, logger)
        return []

    if item.extra.get("skip_download"):
        if not args.no_description:
            export_description(item.description_text, item_dir / "description.txt")
        if not args.no_json:
            export_json(item, item_dir / f"{item_name}.json", [])
        if summary:
            summary.add_item(item, item_dir, downloaded_files=[])
        return []

    plan, track_title_map = build_download_plan(item, args, session, rate_limiter, logger)
    if not plan:
        logger.info("No downloads for %s (%s)", item_display_label(item), item.source_url)
        if not args.no_description:
            export_description(item.description_text, item_dir / "description.txt")
        if not args.no_json:
            export_json(item, item_dir / f"{item_name}.json", [])
        if summary:
            summary.add_item(item, item_dir, downloaded_files=[])
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
        if path.suffix.lower() == ".mp3" and not args.no_id3:
            track_title = track_title_map.get(link.url)
            tag_mp3(path, item, cover_path, track_title, logger)
        if args.format == "unzip" and path.suffix.lower() == ".zip":
            unzip_dir = item_dir / "unzipped"
            ensure_dir(unzip_dir)
            unzip_file(path, unzip_dir, logger)

    if downloaded_files and not args.no_json:
        json_path = item_dir / f"{item_name}.json"
        export_json(item, json_path, downloaded_files)
    if not args.no_description:
        export_description(item.description_text, item_dir / "description.txt")

    if summary:
        summary.add_item(item, item_dir, downloaded_files=downloaded_files)
    if project_tracker and item.extra.get("collection_root"):
        project_tracker.mark_done(item.extra.get("collection_root"), item.title or item_dir.name, logger)

    return downloaded_files


def run_pipeline(
    args: argparse.Namespace,
    urls: list[str],
    logger: logging.Logger,
    reporter: DryRunReporter | None = None,
    summary: SummaryCollector | None = None,
    project_tracker: ProjectProgressTracker | None = None,
) -> tuple[int, int]:
    rate_limiter = RateLimiter(args.sleep)
    output_dir = Path(args.output)
    if not args.dry_run:
        ensure_dir(output_dir)

    session = create_session()
    registry = DownloadRegistry()
    downloaded_total = 0
    item_count = 0
    items_iter = iter_items(urls, session, rate_limiter, args, logger, project_tracker)

    if args.threads <= 1:
        for item in items_iter:
            item_count += 1
            downloaded_total += len(
                download_item(
                    item,
                    args,
                    output_dir,
                    rate_limiter,
                    registry,
                    logger,
                    reporter,
                    summary,
                    project_tracker,
                )
            )
    else:
        from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait

        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = set()
            for item in items_iter:
                item_count += 1
                futures.add(
                    executor.submit(
                        download_item,
                        item,
                        args,
                        output_dir,
                        rate_limiter,
                        registry,
                        logger,
                        reporter,
                        summary,
                        project_tracker,
                    )
                )
                if len(futures) >= args.threads * 2:
                    done, futures = wait(futures, return_when=FIRST_COMPLETED)
                    for future in done:
                        try:
                            downloaded_total += len(future.result())
                        except Exception as exc:
                            logger.error("Worker failed: %s", exc, exc_info=True)

            for future in as_completed(futures):
                try:
                    downloaded_total += len(future.result())
                except Exception as exc:
                    logger.error("Worker failed: %s", exc, exc_info=True)

    return item_count, downloaded_total
