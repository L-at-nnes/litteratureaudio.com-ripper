import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from ..core.models import AudioItem


def export_json(item: AudioItem, output_path: Path, downloaded_files: Iterable[Path]) -> None:
    # JSON is kept self-contained for easy archival.
    data = {
        "tool": "litteratureaudio-ripper",
        "version": "2.0",
        "timestamp": datetime.now().isoformat(),
        "source_url": item.source_url,
        "metadata": {
            "title": item.title,
            "author": item.author,
            "reader": item.reader,
            "series": item.series,
            "language": item.language,
            "duration": item.duration,
            "description": item.description_text,
            "cover_url": item.cover_url,
            "is_collective_project": item.is_collective_project,
        },
        "download_links": [
            {
                "url": link.url,
                "kind": link.kind,
                "filename": link.suggested_filename,
                "final_url": link.final_url,
            }
            for link in item.download_links
        ],
        "tracks": [
            {
                "title": track.title,
                "download_url": track.download_url,
                "page_url": track.page_url,
            }
            for track in item.tracks
        ],
        "downloaded_files": [str(f.name) for f in downloaded_files],
        "extra": item.extra,
    }

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def export_description(description: Optional[str], output_path: Path) -> None:
    if not description:
        return
    output_path.write_text(description.strip() + "\n", encoding="utf-8")
