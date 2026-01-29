import re
import unicodedata
from pathlib import Path

INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*]')
WHITESPACE_RE = re.compile(r'\s+')


def sanitize_filename(name: str, max_length: int = 180) -> str:
    """
    Clean a filename for safe use on Windows/Mac/Linux.
    
    - Replaces underscores with spaces (cleaner look)
    - Replaces colons with underscores (Windows forbids colons)
    - Removes forbidden characters (<>"/\\|?*)
    - Collapses multiple spaces into one
    - Truncates at max_length while preserving word boundaries
    """
    if not name:
        return "untitled"
    # Windows does not allow ":" in filenames; replace it while preserving readability.
    name = name.replace(":", "COLON_TOKEN")
    name = name.replace("_", " ")
    name = name.replace("COLON_TOKEN", "_")
    name = INVALID_CHARS_RE.sub('', name)
    name = WHITESPACE_RE.sub(' ', name).strip()
    if len(name) > max_length:
        cut = name[:max_length]
        if ' ' in cut:
            cut = cut.rsplit(' ', 1)[0]
        name = cut
    return name or "untitled"


def slug_from_url(url: str) -> str:
    if not url:
        return ""
    tail = url.rstrip('/').split('/')[-1]
    if tail.endswith('.html'):
        tail = tail[:-5]
    return tail


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    return WHITESPACE_RE.sub(' ', text).strip()


def strip_accents(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def format_size(size_bytes: int, unit: str = "auto") -> str:
    """
    Format a file size for display.
    
    Args:
        size_bytes: Size in bytes.
        unit: "kb" for KB, "mb" for MB, "auto" for auto-detect.
    
    Returns:
        Human-readable size string (e.g. "3.5 Mo", "125 Ko").
    """
    if size_bytes is None or size_bytes < 0:
        return "? octets"
    
    if unit == "kb":
        return f"{size_bytes / 1024:.1f} Ko"
    elif unit == "mb":
        return f"{size_bytes / (1024 * 1024):.2f} Mo"
    else:
        # Auto: use KB for small files, MB for larger
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} Ko"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} Mo"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def unique_path(base: Path) -> Path:
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    parent = base.parent
    for i in range(1, 1000):
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return base
