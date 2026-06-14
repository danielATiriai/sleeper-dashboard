"""Shared HTTP + file helpers for the ETL (retries, rate-limit handling, JSON IO)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "sleeper-dashboard-etl/0.1 (+local analysis)"})


def get_json(url: str, *, params: dict | None = None, retries: int = 4,
             delay: float = 0.06, timeout: int = 45) -> Any:
    """GET JSON with exponential backoff on 429/5xx. Returns None on HTTP 404."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = _SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                wait = (2 ** attempt) * 0.5 + 0.25
                time.sleep(wait)
                continue
            r.raise_for_status()
            time.sleep(delay)
            return r.json()
        except (requests.RequestException, ValueError) as exc:  # ValueError = bad JSON
            last_exc = exc
            time.sleep((2 ** attempt) * 0.5 + 0.25)
    raise RuntimeError(f"GET failed after {retries} attempts: {url}") from last_exc


def download(url: str, dest: Path, *, retries: int = 4, timeout: int = 120,
             force: bool = False) -> Path:
    """Stream a (possibly large) file to disk, with retries. Caches by default."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force and dest.stat().st_size > 0:
        return dest
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            with _SESSION.get(url, stream=True, timeout=timeout) as r:
                if r.status_code == 404:
                    raise FileNotFoundError(f"404 Not Found: {url}")
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
                tmp.replace(dest)
            return dest
        except FileNotFoundError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep((2 ** attempt) * 0.75 + 0.5)
    raise RuntimeError(f"download failed after {retries} attempts: {url}") from last_exc


def save_json(obj: Any, path: Path, *, slim: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        if slim:
            json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
        else:
            json.dump(obj, f, indent=2, ensure_ascii=False)
    return path


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)
