from dataclasses import dataclass, field
from typing import Literal, Optional


DownloadKind = Literal[
    "mp3",
    "zip",
    "m3u",
    "api",
    "nonce_endpoint",
    "download_token",
    "direct",
    "unknown",
]


@dataclass
class DownloadLink:
    url: str
    kind: DownloadKind = "unknown"
    suggested_filename: Optional[str] = None
    size_bytes: Optional[int] = None
    resolved: bool = False
    final_url: Optional[str] = None


@dataclass
class TrackItem:
    title: str
    download_url: str
    page_url: Optional[str] = None


@dataclass
class AudioItem:
    source_url: str
    page_type: Literal["work", "author_listing", "reader_listing", "track", "unknown"]

    title: Optional[str] = None
    author: Optional[str] = None
    reader: Optional[str] = None
    series: Optional[str] = None
    language: str = "fr"
    duration: Optional[str] = None
    description_text: Optional[str] = None
    cover_url: Optional[str] = None

    post_id: Optional[int] = None

    download_links: list[DownloadLink] = field(default_factory=list)
    tracks: list[TrackItem] = field(default_factory=list)
    collection_urls: list[str] = field(default_factory=list)

    is_collective_project: bool = False
    chapter_urls: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
