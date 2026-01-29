import logging
import re
import time
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1
from mutagen.mp3 import MP3

from .http import RateLimiter, head_request
from ..core.models import AudioItem, DownloadLink, TrackItem
from ..core.utils import format_size, sanitize_filename, unique_path


FILENAME_RE = re.compile(r'filename\*?=\"?([^";]+)\"?')


def guess_kind_from_name(name: Optional[str], content_type: Optional[str]) -> str:
    if name:
        lowered = name.lower()
        if lowered.endswith('.mp3'):
            return 'mp3'
        if lowered.endswith('.zip'):
            return 'zip'
        if lowered.endswith('.m3u') or lowered.endswith('.m3u8'):
            return 'm3u'
    if content_type:
        ct = content_type.lower()
        if 'audio' in ct:
            return 'mp3'
        if 'zip' in ct or 'application/octet-stream' in ct:
            return 'zip'
    return 'unknown'


def resolve_link(session: requests.Session, link: DownloadLink, rate_limiter: RateLimiter, logger: logging.Logger) -> DownloadLink:
    """
    Figure out what a download link actually points to.
    
    The site uses various redirect schemes:
    - /d?nonce=xxx -> redirects to the actual MP3
    - ?download=xxx -> download token that redirects
    - Direct .mp3/.zip links -> no resolution needed
    
    We do a HEAD request to follow redirects and get:
    - The final URL
    - The suggested filename (from Content-Disposition header)
    - The file size
    - The actual file type (mp3, zip, etc.)
    
    This avoids downloading files just to figure out what they are.
    """
    if link.resolved:
        return link
    if link.kind in ['mp3', 'zip', 'm3u', 'direct']:
        link.resolved = True
        link.final_url = link.url
        return link

    try:
        # HEAD lets us resolve redirects and content-disposition without downloading the file.
        response = head_request(session, link.url, rate_limiter)
        content_disp = response.headers.get('Content-Disposition', '')
        filename = None
        if content_disp:
            match = FILENAME_RE.search(content_disp)
            if match:
                filename = match.group(1)
        link.final_url = response.url
        link.suggested_filename = filename
        link.size_bytes = response.headers.get('Content-Length')
        link.kind = guess_kind_from_name(filename or response.url, response.headers.get('Content-Type'))
        link.resolved = True
    except Exception as exc:
        logger.warning("HEAD failed for %s: %s", link.url, exc)
    return link


def derive_filename(link: DownloadLink, response: requests.Response) -> str:
    if link.suggested_filename:
        return link.suggested_filename
    content_disp = response.headers.get('Content-Disposition', '')
    if content_disp:
        match = FILENAME_RE.search(content_disp)
        if match:
            return match.group(1)
    parsed = urlparse(response.url)
    name = Path(parsed.path).name
    if name:
        return name
    return 'download'


def download_file(
    session: requests.Session,
    url: str,
    dest_dir: Path,
    rate_limiter: RateLimiter,
    logger: logging.Logger,
    suggested_filename: Optional[str] = None,
) -> Optional[Path]:
    """
    Download a file with retry logic.
    
    - Tries up to 3 times if something fails
    - Uses a .part temp file to avoid corrupt half-downloads
    - Logs each retry so you know what's happening
    - Respects rate limiting to be polite to the server
    
    Returns the path to the downloaded file, or None if all attempts failed.
    """
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        temp_path = None
        try:
            if attempt > 1:
                logger.info("Retry (%s/%s) for %s", attempt, max_attempts, url)
            rate_limiter.wait()
            response = session.get(url, stream=True, timeout=(10, 120))
            response.raise_for_status()
            filename = suggested_filename or derive_filename(DownloadLink(url=url), response)
            filename = sanitize_filename(filename)
            dest_path = dest_dir / filename
            dest_path = unique_path(dest_path)
            # Write to a temporary file first to avoid half-written outputs.
            temp_path = dest_path.with_suffix(dest_path.suffix + '.part')
            total = 0
            with temp_path.open('wb') as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    total += len(chunk)
            temp_path.replace(dest_path)
            logger.info("Downloaded %s (%s)", dest_path.name, format_size(total, "mb"))
            return dest_path
        except Exception as exc:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            if attempt < max_attempts:
                logger.warning("Download failed, will retry (%s/%s) for %s: %s", attempt, max_attempts, url, exc)
                time.sleep(attempt)
                continue
            logger.error("Failed download after %s attempts %s: %s", max_attempts, url, exc, exc_info=True)
            return None


def download_cover(
    session: requests.Session,
    url: str,
    dest_dir: Path,
    rate_limiter: RateLimiter,
    logger: logging.Logger,
) -> Optional[Path]:
    """
    Download the cover image with retry logic.
    
    Tries up to 3 times if the download fails.
    Detects image type from Content-Type header (jpg, png, webp).
    
    Returns the path to the saved cover, or None if all attempts failed.
    """
    if not url:
        return None
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            if attempt > 1:
                logger.info("Retry cover (%s/%s) for %s", attempt, max_attempts, url)
            rate_limiter.wait()
            response = session.get(url, stream=True, timeout=20)
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', '')
            ext = '.jpg'
            if 'png' in content_type:
                ext = '.png'
            elif 'webp' in content_type:
                ext = '.webp'
            filename = f'cover{ext}'
            dest_path = dest_dir / filename
            total = 0
            with dest_path.open('wb') as handle:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        handle.write(chunk)
                        total += len(chunk)
            logger.info("Downloaded cover %s (%s)", dest_path.name, format_size(total, "kb"))
            return dest_path
        except Exception as exc:
            if attempt < max_attempts:
                logger.warning("Cover download failed, will retry (%s/%s): %s", attempt, max_attempts, exc)
                time.sleep(attempt)
                continue
            logger.warning("Cover download failed after %s attempts: %s", max_attempts, exc)
            return None


def tag_mp3(mp3_path: Path, item: AudioItem, cover_path: Optional[Path], track_title: Optional[str], logger: logging.Logger) -> None:
    """
    Write ID3 tags to an MP3 file.
    
    Tags written:
    - TIT2 (Title): track title if available, else the audiobook title
    - TPE1 (Artist): reader name, fallback to author, fallback to "Unknown"
    - TALB (Album): the audiobook title
    - APIC (Cover): embedded album art if we have a cover image
    
    Won't crash if tagging fails - just logs a warning.
    """
    try:
        audio = MP3(mp3_path, ID3=ID3)
        try:
            audio.add_tags()
        except Exception:
            pass  # Tags might already exist, that's fine

        # Prefer track title, fallback to the item title.
        title = track_title or item.title
        if title:
            audio.tags.add(TIT2(encoding=3, text=title))

        artist = item.reader or item.author or "Unknown"
        audio.tags.add(TPE1(encoding=3, text=artist))

        album = item.title or title
        if album:
            audio.tags.add(TALB(encoding=3, text=album))

        if cover_path and cover_path.exists():
            with cover_path.open('rb') as img:
                mime = 'image/jpeg'
                if cover_path.suffix.lower() == '.png':
                    mime = 'image/png'
                elif cover_path.suffix.lower() == '.webp':
                    mime = 'image/webp'
                audio.tags.add(
                    APIC(
                        encoding=3,
                        mime=mime,
                        type=3,
                        desc='Cover',
                        data=img.read(),
                    )
                )

        audio.save()
        logger.debug("Tagged %s", mp3_path.name)
    except Exception as exc:
        logger.warning("ID3 tagging failed for %s: %s", mp3_path.name, exc)


def unzip_file(zip_path: Path, dest_dir: Path, logger: logging.Logger) -> list[Path]:
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(dest_dir)
            for name in zf.namelist():
                extracted.append(dest_dir / name)
        logger.info("Unzipped %s", zip_path.name)
    except Exception as exc:
        logger.error("Unzip failed for %s: %s", zip_path.name, exc)
    return extracted


def build_track_links(tracks: list[TrackItem]) -> list[DownloadLink]:
    links: list[DownloadLink] = []
    for track in tracks:
        links.append(DownloadLink(url=track.download_url, kind='nonce_endpoint'))
    return links
