import re
import unicodedata
from pathlib import Path

INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*]')
WHITESPACE_RE = re.compile(r'\s+')


def sanitize_filename(name: str, max_length: int = 180) -> str:
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
