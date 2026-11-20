"""Polite HTTP for public archives: identify ourselves, cache, back off, retry."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import requests

USER_AGENT = "TimeCapsule-NewsArchive-Research/0.2"
CACHE_DIR = Path(os.environ.get("TIMECAPSULE_CACHE", "data/cache"))

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_call: dict[str, float] = {}


def get(url: str, *, params: dict | None = None, min_interval: float = 1.0, timeout: int = 120,
        retries: int = 4, cache: bool = True) -> bytes:
    """GET with an on-disk cache, a per-host rate limit and exponential backoff."""
    req = requests.Request("GET", url, params=params).prepare()
    full = req.url
    key = hashlib.sha1(full.encode()).hexdigest()
    path = CACHE_DIR / key[:2] / key
    if cache and path.exists():
        return path.read_bytes()

    host = requests.utils.urlparse(full).netloc
    delay = 2.0
    for attempt in range(retries + 1):
        wait = _last_call.get(host, 0) + min_interval - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.time()
        try:
            r = _session.get(full, timeout=timeout)
            if r.status_code == 200:
                if cache:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(r.content)
                return r.content
            if r.status_code not in (429, 500, 502, 503, 504):
                r.raise_for_status()
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
            if attempt == retries:
                raise
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"giving up on {full}")
