"""HTTP downloads with retries, back-off and an on-disk cache that records provenance.

Every downloaded file is kept unchanged under ``data/raw/<source>/`` next to a
``<file>.meta.json`` record (URL, time, size, SHA-256, HTTP status). A file that is
already cached is reused unless ``refresh=True``, so the pipeline can be rebuilt
offline from the raw files.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import USER_AGENT


class DownloadError(RuntimeError):
    pass


def session(total_retries: int = 5, backoff: float = 1.5) -> requests.Session:
    retry = Retry(total=total_retries, connect=total_retries, read=total_retries, status=total_retries,
                  backoff_factor=backoff, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset({"GET"}), respect_retry_after_header=True, raise_on_status=False)
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, application/pdf, */*"})
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_meta(path: Path, url: str, status: int | None, note: str = "") -> dict:
    meta = {
        "file": path.name,
        "url": url,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "http_status": status,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "note": note,
    }
    path.with_name(path.name + ".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def read_meta(path: Path) -> dict:
    m = path.with_name(path.name + ".meta.json")
    return json.loads(m.read_text(encoding="utf-8")) if m.exists() else {}


def download(url: str, dest: Path, *, params: dict | None = None, refresh: bool = False,
             sess: requests.Session | None = None, timeout: float = 120, min_bytes: int = 1) -> Path:
    """Download ``url`` to ``dest`` (cached). Raises DownloadError rather than writing a partial file."""
    if dest.exists() and not refresh and dest.stat().st_size >= min_bytes:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    sess = sess or session()
    try:
        r = sess.get(url, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise DownloadError(f"{url}: {type(e).__name__}: {e}") from e
    if r.status_code != 200:
        raise DownloadError(f"{r.url}: HTTP {r.status_code}")
    if len(r.content) < min_bytes:
        raise DownloadError(f"{r.url}: response too small ({len(r.content)} bytes)")
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    write_meta(dest, r.url, r.status_code)
    time.sleep(0.2)   # be polite to official servers
    return dest


def pdf_problem(path: Path) -> str | None:
    """Return a description of what is wrong with a PDF, or None if it looks complete.

    A download that was interrupted is the usual culprit: the file then lacks the closing
    %%EOF marker and its cross-reference table cannot be read.
    """
    if not path.exists():
        return "file missing"
    with open(path, "rb") as f:
        head = f.read(8)
        f.seek(max(0, path.stat().st_size - 2048))
        tail = f.read()
    if not head.startswith(b"%PDF-"):
        return "not a PDF file"
    if b"%%EOF" not in tail:
        return (f"incomplete download: no end-of-file marker ({path.stat().st_size:,} bytes); "
                "download the report again")
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return "PDF has no readable pages"
    except Exception as e:                          # pdfminer raises many exception types
        return f"PDF cannot be read: {type(e).__name__}"
    return None
