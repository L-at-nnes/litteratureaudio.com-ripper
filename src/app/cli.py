import argparse
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from .logging_utils import setup_logging
from .pipeline import run_pipeline
from ..report.reporting import DryRunReporter, ProjectProgressTracker, SummaryCollector
from .verify import verify_output


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    parts = parts._replace(fragment="")
    return urlunsplit(parts)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="litteratureaudio.com ripper")
    parser.add_argument("urls", nargs="*", help="URLs to process")
    parser.add_argument("--txt", dest="txt_file", help="Text file with one URL per line")
    parser.add_argument("--output", default="./dl", help="Output folder")
    parser.add_argument("--threads", type=int, default=4, help="Number of worker threads")
    parser.add_argument("--sequential", action="store_true", help="Download one file at a time (easier to read logs)")
    parser.add_argument("--sleep", type=float, default=0, help="Delay between requests (seconds)")
    parser.add_argument(
        "--format",
        default="default",
        choices=["default", "mp3", "zip", "mp3+zip", "all", "unzip"],
        help="Download policy",
    )
    parser.add_argument("--no-json", action="store_true", help="Do not export JSON metadata")
    parser.add_argument("--no-cover", action="store_true", help="Do not download cover images")
    parser.add_argument("--no-description", action="store_true", help="Do not export description.txt")
    parser.add_argument("--no-id3", action="store_true", help="Do not write ID3 tags")
    parser.add_argument("--max-pages", type=int, default=0, help="Limit pagination for listings")
    parser.add_argument("--dry-run", action="store_true", help="Extract only (no files written)")
    parser.add_argument("--metadata-only", action="store_true", help="Download cover/description/JSON only")
    parser.add_argument(
        "--summary-report",
        nargs="?",
        const="summary-report.json",
        default=None,
        help="Write summary report JSON to PATH (default: summary-report.json)",
    )
    parser.add_argument(
        "--csv-report",
        nargs="?",
        const="report.csv",
        default=None,
        help="Write CSV report to PATH (default: report.csv)",
    )
    parser.add_argument("--verify", dest="verify_path", help="Verify a folder and report missing tracks")
    parser.add_argument(
        "--no-duplicates",
        action="store_true",
        help="Create relative shortcuts for duplicate albums instead of re-downloading",
    )
    return parser.parse_args(argv)


def load_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls)
    if args.txt_file:
        with open(args.txt_file, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                urls.append(line)
    return [normalize_url(u) for u in urls if u]


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    logger = setup_logging()

    if args.verify_path:
        return verify_output(Path(args.verify_path), logger)

    urls = load_urls(args)
    if not urls:
        logger.error("No URL provided")
        return 1

    reporter = DryRunReporter(Path("dry-run-report.log")) if args.dry_run else None
    summary = None
    if args.summary_report or args.csv_report:
        mode = "dry-run" if args.dry_run else "metadata-only" if args.metadata_only else "download"
        summary = SummaryCollector(mode=mode, capture_rows=bool(args.csv_report))
    project_tracker = ProjectProgressTracker()

    item_count, downloaded_total = run_pipeline(
        args,
        urls,
        logger,
        reporter=reporter,
        summary=summary,
        project_tracker=project_tracker,
    )

    if item_count == 0:
        logger.warning("No items found")
        return 0

    if args.dry_run and reporter:
        logger.info("Dry-run report: %s", reporter.path)

    if summary and args.summary_report:
        summary.write_summary(Path(args.summary_report))
        logger.info("Summary report: %s", args.summary_report)

    if summary and args.csv_report:
        summary.write_csv(Path(args.csv_report))
        logger.info("CSV report: %s", args.csv_report)

    logger.info("Downloaded %s files to %s", downloaded_total, Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
