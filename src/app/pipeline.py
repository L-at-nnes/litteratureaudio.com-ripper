"""
Main pipeline entry point: orchestrates the full download process.

This module provides run_pipeline(), the main entry point that:
1. Processes URLs one project at a time
2. Scrapes metadata for each project
3. Downloads files (with optional multithreading)

The heavy lifting is delegated to:
- scraper.py: URL crawling and metadata extraction
- downloader_pipeline.py: File downloading and tagging
- registry.py: Deduplication tracking
"""

import argparse
import logging
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from pathlib import Path

from ..core.utils import ensure_dir
from ..infra.http import RateLimiter, create_session
from ..report.reporting import DryRunReporter, ProjectProgressTracker, SummaryCollector

from .downloader_pipeline import download_item
from .registry import DownloadRegistry, FolderRegistry
from .scraper import iter_items


def run_pipeline(
    args: argparse.Namespace,
    urls: list[str],
    logger: logging.Logger,
    reporter: DryRunReporter | None = None,
    summary: SummaryCollector | None = None,
    project_tracker: ProjectProgressTracker | None = None,
) -> tuple[int, int]:
    """
    Main entry point: process all URLs and download everything.
    
    Key behavior: Projects are processed ONE AT A TIME.
    
    Why? Because if you give it 3 URLs, you want to see:
      1. Scrape Project A metadata
      2. Download all of Project A
      3. Scrape Project B metadata
      4. Download all of Project B
      etc.
    
    NOT:
      1. Scrape A, B, C metadata (interleaved)
      2. Download A, B, C (interleaved)
    
    Multithreading is used WITHIN each project (multiple MP3s in parallel),
    but projects themselves are sequential.
    
    Returns (item_count, downloaded_file_count).
    """
    rate_limiter = RateLimiter(args.sleep)
    output_dir = Path(args.output)
    if not args.dry_run:
        ensure_dir(output_dir)

    session = create_session()
    registry = DownloadRegistry()
    folder_registry = FolderRegistry() if getattr(args, 'no_duplicates', False) else None
    downloaded_total = 0
    item_count = 0

    # Process ONE project at a time: scrape all metadata, then download all files
    # This keeps the console output clean and predictable
    for url in urls:
        project_items = list(iter_items([url], session, rate_limiter, args, logger, project_tracker))
        
        if args.threads <= 1:
            for item in project_items:
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
                        folder_registry,
                    )
                )
        else:
            with ThreadPoolExecutor(max_workers=args.threads) as executor:
                futures = set()
                for item in project_items:
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
                            folder_registry,
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
