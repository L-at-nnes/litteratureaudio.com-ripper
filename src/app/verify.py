import json
import logging
from pathlib import Path

from ..core.utils import sanitize_filename


def normalize_for_match(text: str) -> str:
    cleaned = sanitize_filename(text or "")
    return "".join(ch.lower() for ch in cleaned if ch.isalnum())


def verify_output(root: Path, logger: logging.Logger) -> int:
    if not root.exists():
        logger.error("Verify path does not exist: %s", root)
        return 1

    json_files = list(root.rglob("*.json"))
    if not json_files:
        logger.warning("No JSON metadata found under %s", root)
        return 0

    missing_files = 0
    missing_tracks = 0
    scanned = 0

    for json_path in json_files:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("VERIFY: failed to read %s: %s", json_path, exc)
            continue

        scanned += 1
        meta = data.get("metadata", {})
        title = meta.get("title") or json_path.stem
        author = meta.get("author") or "Unknown"
        item_dir = json_path.parent
        label = f"Author: {author} | Book: {title}"

        expected_files = data.get("downloaded_files") or []
        if expected_files:
            for name in expected_files:
                if not (item_dir / name).exists():
                    missing_files += 1
                    logger.warning("VERIFY: missing file %s | %s | dir=%s", name, label, item_dir)

        tracks = data.get("tracks") or []
        has_zip = any(str(name).lower().endswith(".zip") for name in expected_files)
        has_mp3 = any(str(name).lower().endswith(".mp3") for name in expected_files)
        if tracks and not expected_files:
            logger.info("VERIFY: no downloaded_files for %s (skipping track check)", label)
        elif tracks and has_zip and not has_mp3:
            logger.info("VERIFY: zip-only entry for %s (skipping track check)", label)
        elif tracks:
            mp3_files = list(item_dir.glob("*.mp3"))
            if len(mp3_files) < len(tracks):
                missing = len(tracks) - len(mp3_files)
                missing_tracks += missing
                logger.warning(
                    "VERIFY: missing tracks for %s | expected=%s found=%s | dir=%s",
                    label,
                    len(tracks),
                    len(mp3_files),
                    item_dir,
                )

                stems = [normalize_for_match(p.stem) for p in mp3_files]
                missing_titles = []
                for track in tracks:
                    title_text = track.get("title") if isinstance(track, dict) else None
                    norm = normalize_for_match(title_text or "")
                    if norm and not any(norm in stem for stem in stems):
                        missing_titles.append(title_text)
                if missing_titles:
                    sample = ", ".join(t for t in missing_titles[:5] if t)
                    if sample:
                        logger.info("VERIFY: missing titles (sample): %s", sample)

    logger.info(
        "VERIFY SUMMARY: json=%s missing_files=%s missing_tracks=%s",
        scanned,
        missing_files,
        missing_tracks,
    )
    return 1 if missing_files or missing_tracks else 0
