import re
from typing import Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..core.models import AudioItem, DownloadLink, TrackItem
from ..core.utils import normalize_text, slug_from_url, strip_accents


AUTHOR_LISTING_RE = re.compile(r"^https?://www\.litteratureaudio\.com/livre-audio-gratuit-mp3/auteur/([^/?#]+)(?:/page/(\d+))?/?$")
WORK_PAGE_RE = re.compile(r"^https?://www\.litteratureaudio\.com/livre-audio-gratuit-mp3/([^/?#]+)\.html(?:$|\?)")
VOICE_LISTING_RE = re.compile(r"^https?://www\.litteratureaudio\.com/livre-audio-gratuit-mp3/voix/([^/?#]+)(?:/page/(\d+))?/?$")
MEMBER_LISTING_RE = re.compile(r"^https?://www\.litteratureaudio\.com/membre/([^/?#]+)(?:/page/(\d+))?/?$")
TRACK_RE = re.compile(r"/livre-audio-gratuit-mp3/piste/")


META_DURATION_RE = re.compile(r"Duree\s*:\s*([^.]+)", re.IGNORECASE)
TITLE_SPLIT_RE = re.compile(r"^([^-]+?)\s*-\s*(.+)$")
POST_ID_RE = re.compile(r"postid-(\d+)")
PWC_POST_ID_RE = re.compile(r"postID\":(\d+)")


PARSER_PREFERENCE = ["lxml", "html.parser"]


def make_soup(html: str) -> BeautifulSoup:
    for parser in PARSER_PREFERENCE:
        try:
            return BeautifulSoup(html, parser)
        except Exception:
            continue
    return BeautifulSoup(html, "html.parser")


def detect_page_type(url: str, html: str) -> str:
    if AUTHOR_LISTING_RE.match(url):
        return "author_listing"
    if VOICE_LISTING_RE.match(url):
        return "voice_listing"
    if MEMBER_LISTING_RE.match(url):
        return "member_listing"
    if TRACK_RE.search(url):
        return "track"
    if WORK_PAGE_RE.match(url):
        return "work"
    if "entry-title" in html and "/auteur/" in html:
        return "author_listing"
    return "unknown"


def extract_listing_name(soup: BeautifulSoup, page_type: str) -> Optional[str]:
    if page_type in ["author_listing", "voice_listing"]:
        header = soup.find("h1", class_="archive-title")
        text = header.get_text(" ", strip=True) if header else ""
        if ":" in text:
            return normalize_text(text.split(":", 1)[1])
        return normalize_text(text) or None

    if page_type == "member_listing":
        h1 = soup.find("h1", class_="entry-title") or soup.find("h1")
        if h1:
            return normalize_text(h1.get_text(" ", strip=True))
    return None


def extract_post_id(soup: BeautifulSoup, html: str) -> Optional[int]:
    body = soup.find("body")
    if body and body.get("class"):
        for cls in body.get("class"):
            if cls.startswith("postid-"):
                try:
                    return int(cls.split("-", 1)[1])
                except ValueError:
                    pass

    match = POST_ID_RE.search(html)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    match = PWC_POST_ID_RE.search(html)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    tag = soup.find(attrs={"data-play-id": True})
    if tag:
        try:
            return int(tag.get("data-play-id"))
        except (TypeError, ValueError):
            pass

    return None


def extract_title(soup: BeautifulSoup) -> Optional[str]:
    title_tag = soup.find("title")
    if title_tag and title_tag.text:
        title = title_tag.text.replace(" | Litteratureaudio.com", "").strip()
        match = TITLE_SPLIT_RE.match(title)
        if match:
            return normalize_text(match.group(2))
        return normalize_text(title)

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].replace(" | Litteratureaudio.com", "").strip()
        match = TITLE_SPLIT_RE.match(title)
        if match:
            return normalize_text(match.group(2))
        return normalize_text(title)

    h1 = soup.find("h1", class_="entry-title")
    if h1:
        return normalize_text(h1.get_text(strip=True))
    return None


def extract_author(soup: BeautifulSoup) -> Optional[str]:
    author_span = soup.find("span", class_="entry-auteur")
    if author_span:
        link = author_span.find("a", rel="tag")
        if link:
            return normalize_text(link.get_text(strip=True))

    title_tag = soup.find("title")
    if title_tag and title_tag.text:
        match = TITLE_SPLIT_RE.match(title_tag.text)
        if match:
            author = normalize_text(match.group(1))
            if "," in author:
                parts = author.split(",", 1)
                return normalize_text(f"{parts[1].strip()} {parts[0].strip()}")
            return author
    return None


def extract_reader(soup: BeautifulSoup) -> Optional[str]:
    reader_span = soup.find("span", class_="entry-voix")
    if reader_span:
        link = reader_span.find("a", rel="tag")
        if link:
            return normalize_text(link.get_text(strip=True))
    return None


def extract_cover_url(soup: BeautifulSoup) -> Optional[str]:
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"]
    return None


def extract_description(soup: BeautifulSoup) -> Optional[str]:
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        return normalize_text(meta_desc["content"])

    entry = soup.find("div", class_="entry-content")
    if entry:
        for tag in entry.find_all(["script", "ins", "style"]):
            tag.decompose()
        text = entry.get_text(separator="\n", strip=True)
        return normalize_text(text)[:1000]
    return None


def extract_duration(soup: BeautifulSoup) -> Optional[str]:
    duration_span = soup.find("span", class_="play-duration")
    if duration_span:
        return normalize_text(duration_span.get_text(strip=True))

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        # The site embeds the duration as "Duree:" inside the meta description.
        content = meta_desc.get("content", "")
        content = strip_accents(content)
        match = META_DURATION_RE.search(content)
        if match:
            return normalize_text(match.group(1))
    return None


def extract_download_links(scope: BeautifulSoup, page_url: str) -> list[DownloadLink]:
    links: list[DownloadLink] = []

    def normalize_page_url(url: str) -> str:
        parts = urlsplit(url)
        parts = parts._replace(query="", fragment="")
        return urlunsplit(parts).rstrip("/")

    buttons = scope.find_all("a", class_=lambda c: c and "btn-download" in c)
    normalized_page = normalize_page_url(page_url)
    matched = []
    for btn in buttons:
        data_url = btn.get("data-url")
        if data_url and normalize_page_url(data_url) == normalized_page:
            matched.append(btn)

    if matched:
        buttons = matched
    elif buttons:
        buttons = [buttons[0]]

    for a in buttons:
        href = a.get("href")
        if not href:
            continue
        # Links can be nonce endpoints or download tokens; resolve later via HEAD.
        full_url = urljoin(page_url, href)
        kind = "download_token" if "?download=" in full_url else "nonce_endpoint" if "/d?nonce=" in full_url else "unknown"
        links.append(DownloadLink(url=full_url, kind=kind))

    return links


def extract_track_items(scope: BeautifulSoup, page_url: str) -> list[TrackItem]:
    tracks: list[TrackItem] = []

    entry = scope.find("div", class_="entry-content")
    if entry and entry.find("article", class_=lambda c: c and ("station" in c or "type-station" in c)):
        container = entry
    else:
        container = scope

    for article in container.find_all("article"):
        classes = article.get("class") or []
        if "station" not in classes and "type-station" not in classes:
            continue
        title_tag = article.find(["h2", "h3", "h4"], class_="entry-title")
        title = normalize_text(title_tag.get_text(strip=True)) if title_tag else ""
        download = article.find("a", class_=lambda c: c and "btn-download" in c)
        if not download or not download.get("href"):
            continue
        dl_url = urljoin(page_url, download["href"])
        page_link = None
        link_tag = article.find("a", href=True)
        if link_tag and "/piste/" in link_tag.get("href", ""):
            page_link = urljoin(page_url, link_tag["href"])
        tracks.append(TrackItem(title=title, download_url=dl_url, page_url=page_link))
    return tracks


def extract_loop_more_url(soup: BeautifulSoup) -> Optional[str]:
    link = soup.find("a", class_=lambda c: c and "scroller" in c and "no-ajax" in c)
    if link and link.get("href"):
        return link["href"]
    return None


def extract_author_slug(soup: BeautifulSoup) -> Optional[str]:
    author_span = soup.find("span", class_="entry-auteur")
    if author_span:
        link = author_span.find("a", href=True)
        if link and "/auteur/" in link["href"]:
            return link["href"].rstrip("/").split("/auteur/")[-1]

    body = soup.find("body")
    if body and body.get("class"):
        for cls in body.get("class"):
            if cls.startswith("auteur-"):
                slug = cls.split("-", 1)[1]
                if slug.startswith("auteur-"):
                    slug = slug.split("-", 1)[1]
                return slug
    return None


def is_collection_page(soup: BeautifulSoup, url: str, title: Optional[str], description: Optional[str]) -> bool:
    body = soup.find("body")
    if body and body.get("class"):
        for cls in body.get("class"):
            if "sommaire" in cls:
                return True
    entry = soup.find("div", class_="entry-content")
    if entry:
        station = entry.find("div", class_="station-content")
        if station:
            block = station.find("div", class_="block-loop-items")
            if block:
                links = {
                    a["href"]
                    for a in block.find_all("a", href=True)
                    if "/livre-audio-gratuit-mp3/" in a["href"] and a["href"].endswith(".html")
                }
                if len(links) >= 3:
                    return True
    lowered_url = (url or "").lower()
    if "oeuvre-integrale" in lowered_url:
        return True
    text = f"{title or ''} {description or ''}".lower()
    keywords = ["oeuvre integrale", "sommaire", "projet collectif"]
    return any(keyword in text for keyword in keywords)


def extract_collection_urls(soup: BeautifulSoup, page_url: str, author_slug: Optional[str]) -> list[str]:
    entry = soup.find("div", class_="entry-content")
    if not entry:
        return []

    station = entry.find("div", class_="station-content")
    
    # Count all livre-audio links in station-content to decide if block-loop-items is complete.
    total_station_links = set()
    if station:
        for a in station.find_all("a", href=True):
            href = a["href"]
            if "/livre-audio-gratuit-mp3/" in href and href.endswith(".html"):
                full_url = urljoin(page_url, href)
                if full_url != page_url:
                    total_station_links.add(full_url)
    
    if station:
        block = station.find("div", class_="block-loop-items")
        if block:
            links = set()
            for a in block.find_all("a", href=True):
                href = a["href"]
                if "/livre-audio-gratuit-mp3/" in href and href.endswith(".html"):
                    full_url = urljoin(page_url, href)
                    if full_url != page_url:
                        links.add(full_url)
            # Only use block-loop-items if it has MOST of the links (>70%)
            # Otherwise there are probably more links in plain paragraphs.
            if links and len(links) >= len(total_station_links) * 0.7:
                return sorted(links)

    # Prefer block-loop-items sections that match collection slug tokens.
    slug_tokens = set()
    slug = slug_from_url(page_url)
    if slug:
        tokens = slug.split("-")
        stop = {
            "oeuvre",
            "integrale",
            "integral",
            "tome",
            "tomes",
            "livre",
            "audio",
            "gratuit",
            "mp3",
            "et",
            "de",
            "du",
            "des",
            "la",
            "le",
            "les",
            "a",
            "au",
            "aux",
            "d",
            "l",
        }
        author_tokens = author_slug.split("-") if author_slug else []
        slug_tokens = {t for t in tokens if t and t not in stop and t not in author_tokens}

    blocks = entry.find_all("div", class_="block-loop-items")
    best_links: set[str] = set()
    best_score = 0
    if blocks and slug_tokens:
        for block in blocks:
            block_links = set()
            score = 0
            for a in block.find_all("a", href=True):
                href = a["href"]
                if "/livre-audio-gratuit-mp3/" not in href or not href.endswith(".html"):
                    continue
                block_links.add(urljoin(page_url, href))
                link_slug = slug_from_url(href)
                if any(token in link_slug for token in slug_tokens):
                    score += 1
            if score > best_score and block_links:
                best_score = score
                best_links = block_links

    # Only use best_links if it covers most of station-content (>50%)
    # Otherwise fall through to collect ALL links from station-content.
    if best_links and len(best_links) >= len(total_station_links) * 0.5:
        return sorted(best_links)

    # Fallback: match slug tokens across all entry-content links (useful for the Bible page).
    # But only use this if we find a significant number of matches.
    if slug_tokens:
        matched = set()
        for a in entry.find_all("a", href=True):
            href = a["href"]
            if "/livre-audio-gratuit-mp3/" not in href or not href.endswith(".html"):
                continue
            link_slug = slug_from_url(href)
            if any(token in link_slug for token in slug_tokens):
                full_url = urljoin(page_url, href)
                if full_url != page_url:
                    matched.add(full_url)
        # Only use slug matching if we found a reasonable number of links (>10)
        # Otherwise fall through to collect ALL links from station-content.
        if len(matched) > 10:
            return sorted(matched)

    # Special case: Bible project.
    if "bible" in slug or "testament" in slug:
        matched = set()
        for a in entry.find_all("a", href=True):
            href = a["href"]
            if "/livre-audio-gratuit-mp3/" not in href or not href.endswith(".html"):
                continue
            if "bible" in href or "testament" in href or "evangile" in href:
                full_url = urljoin(page_url, href)
                if full_url != page_url:
                    matched.add(full_url)
        if matched:
            return sorted(matched)

    # Final fallback: collect ALL livre-audio links from station-content.
    # This handles sommaire pages like "La Comédie humaine" where links don't
    # share slug tokens with the parent page (e.g. individual Balzac works).
    if station:
        all_links = set()
        for a in station.find_all("a", href=True):
            href = a["href"]
            if "/livre-audio-gratuit-mp3/" not in href or not href.endswith(".html"):
                continue
            full_url = urljoin(page_url, href)
            if full_url != page_url:
                all_links.add(full_url)
        if all_links:
            return sorted(all_links)

    links = set()
    for art in entry.find_all("article"):
        classes = art.get("class") or []
        if author_slug and f"auteur-{author_slug}" not in classes:
            continue
        a = art.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if "/livre-audio-gratuit-mp3/" in href and href.endswith(".html"):
            full_url = urljoin(page_url, href)
            if full_url != page_url:
                links.add(full_url)
    return sorted(links)


def find_main_article(soup: BeautifulSoup, post_id: Optional[int]):
    if post_id:
        article = soup.find("article", id=f"post-{post_id}")
        if article:
            return article
    article = soup.find("article", class_=lambda c: c and "post" in c and "entry" in c)
    return article or soup


def extract_listing_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls = set()
    for a in soup.select(".entry-title a[href]"):
        href = a.get("href")
        if not href:
            continue
        full_url = urljoin(base_url, href)
        if "/livre-audio-gratuit-mp3/" in full_url and full_url.endswith(".html"):
            urls.add(full_url)
    return sorted(urls)


def find_next_page(soup: BeautifulSoup) -> Optional[str]:
    for selector in ["a.next", "a.page-numbers.next", "a.next.page-numbers"]:
        link = soup.select_one(selector)
        if link and link.get("href"):
            return link.get("href")
    return None


def parse_work_page(url: str, html: str) -> Tuple[AudioItem, BeautifulSoup]:
    soup = make_soup(html)
    page_type = "track" if TRACK_RE.search(url) else "work"
    item = AudioItem(source_url=url, page_type=page_type)

    # Base metadata from the page HTML.
    item.title = extract_title(soup)
    item.author = extract_author(soup)
    item.reader = extract_reader(soup)
    item.cover_url = extract_cover_url(soup)
    item.description_text = extract_description(soup)
    item.duration = extract_duration(soup)
    item.post_id = extract_post_id(soup, html)

    main_article = find_main_article(soup, item.post_id)
    item.download_links.extend(extract_download_links(main_article, url))
    item.tracks = extract_track_items(main_article, url)
    item.is_collective_project = bool(item.tracks)
    loop_more_url = extract_loop_more_url(soup)
    if loop_more_url:
        item.extra["loop_more_url"] = loop_more_url

    author_slug = extract_author_slug(soup)
    item.extra["author_slug"] = author_slug
    if is_collection_page(soup, url, item.title, item.description_text):
        item.collection_urls = extract_collection_urls(soup, url, author_slug)
        if item.collection_urls:
            item.is_collective_project = True

    return item, soup
