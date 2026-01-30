import csv
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..core.models import AudioItem
from ..core.utils import slug_from_url


@dataclass
class SizeStats:
    files: int = 0
    bytes: int = 0

    def add(self, file_count: int, byte_count: int) -> None:
        self.files += file_count
        self.bytes += byte_count


class SummaryCollector:
    def __init__(self, mode: str, capture_rows: bool) -> None:
        self.mode = mode
        self.capture_rows = capture_rows
        self.lock = threading.Lock()
        self.total = SizeStats()
        self.by_author: dict[str, SizeStats] = {}
        self.by_project: dict[str, SizeStats] = {}
        self.rows: list[dict[str, str | int]] = []

    def add_item(
        self,
        item: AudioItem,
        item_dir: Path,
        downloaded_files: list[Path] | None = None,
        planned_count: int | None = None,
    ) -> None:
        file_count = planned_count if planned_count is not None else len(downloaded_files or [])
        byte_count = 0
        if downloaded_files:
            for path in downloaded_files:
                try:
                    byte_count += path.stat().st_size
                except Exception:
                    continue

        author = item.author or "Unknown"
        project = item.extra.get("collection_root") or item.title or "Unknown"

        with self.lock:
            self.total.add(file_count, byte_count)
            self.by_author.setdefault(author, SizeStats()).add(file_count, byte_count)
            self.by_project.setdefault(project, SizeStats()).add(file_count, byte_count)

            if self.capture_rows:
                self.rows.append(
                    {
                        "source_url": item.source_url,
                        "title": item.title or "",
                        "author": author,
                        "reader": item.reader or "",
                        "project": project,
                        "output_dir": str(item_dir),
                        "track_count": len(item.tracks),
                        "file_count": file_count,
                        "total_bytes": byte_count,
                        "mode": self.mode,
                    }
                )

    def write_summary(self, path: Path) -> None:
        payload = {
            "mode": self.mode,
            "timestamp": datetime.now().isoformat(),
            "total": {"files": self.total.files, "bytes": self.total.bytes},
            "by_author": {
                name: {"files": stats.files, "bytes": stats.bytes}
                for name, stats in sorted(self.by_author.items())
            },
            "by_project": {
                name: {"files": stats.files, "bytes": stats.bytes}
                for name, stats in sorted(self.by_project.items())
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_csv(self, path: Path) -> None:
        if not self.capture_rows:
            return
        fieldnames = [
            "source_url",
            "title",
            "author",
            "reader",
            "project",
            "output_dir",
            "track_count",
            "file_count",
            "total_bytes",
            "mode",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.rows)


class ProjectProgressTracker:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.total_by_project: dict[str, int] = {}
        self.done_by_project: dict[str, int] = {}

    def register(self, project: str, total: int, logger: logging.Logger) -> None:
        if not project or total <= 0:
            return
        with self.lock:
            if project in self.total_by_project:
                return
            self.total_by_project[project] = total
            self.done_by_project[project] = 0
        logger.info("Project detected: %s (items: %s)", project, total)

    def mark_done(self, project: str, book_title: str, logger: logging.Logger) -> None:
        """Track project progress. Logging disabled due to unreliable counting with duplicates."""
        if not project:
            return
        with self.lock:
            if project not in self.total_by_project:
                return
            total = self.total_by_project[project]
            # Cap at total to avoid showing 84/78 type issues when duplicates are processed
            self.done_by_project[project] = min(self.done_by_project[project] + 1, total)
            # Note: Progress logging removed - counter is unreliable when same project
            # appears multiple times (e.g., Zola's Rougon-Macquart referenced from multiple pages)


class DryRunReporter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.path.write_text("", encoding="utf-8-sig")

    def write(self, line: str) -> None:
        # Line-based reports keep memory usage flat even for very large runs.
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def item_display_label(item: AudioItem) -> str:
    title = item.title or slug_from_url(item.source_url) or "item"
    parts: list[str] = []
    if item.author:
        parts.append(f"Author: {item.author}")
    if item.reader:
        parts.append(f"Reader: {item.reader}")

    collection_root = item.extra.get("collection_root")
    if item.extra.get("skip_download"):
        project_name = collection_root or title
        parts.append(f"Project: {project_name}")
    else:
        if collection_root:
            parts.append(f"Project: {collection_root}")
        parts.append(f"Book: {title}")

    return " | ".join(parts) if parts else title
