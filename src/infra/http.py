import threading
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class RateLimiter:
    def __init__(self, sleep_seconds: float = 0) -> None:
        self.sleep_seconds = max(0.0, sleep_seconds)
        self.lock = threading.Lock()
        self.last_request_time = 0.0

    def wait(self) -> None:
        if self.sleep_seconds <= 0:
            return
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.sleep_seconds:
                time.sleep(self.sleep_seconds - elapsed)
            self.last_request_time = time.time()


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    # Keep the scraper resilient to transient HTTP errors.
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_html(session: requests.Session, url: str, rate_limiter: Optional[RateLimiter] = None) -> str:
    if rate_limiter:
        rate_limiter.wait()
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return response.text


def fetch_json(session: requests.Session, url: str, rate_limiter: Optional[RateLimiter] = None):
    if rate_limiter:
        rate_limiter.wait()
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def head_request(session: requests.Session, url: str, rate_limiter: Optional[RateLimiter] = None):
    if rate_limiter:
        rate_limiter.wait()
    response = session.head(url, allow_redirects=True, timeout=20)
    response.raise_for_status()
    return response
