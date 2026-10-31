"""Small data.gov.in client: reads one or more API keys from .env, rotates them across requests,
retries on errors, and never prints or logs a key.

DATA_GOV_IN_API_KEY may hold one key or several separated by commas, spaces or semicolons.
Use `fetch_pages(...)` to download all records of a resource in parallel (one thread per key).
"""

import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import cycle
from pathlib import Path
from threading import Lock

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = "https://api.data.gov.in"
KEY_RE = re.compile(r"[0-9a-fA-F]{32,}")
HEADERS = {"User-Agent": "Mozilla/5.0 (AgriPulse data prep)", "Accept": "application/json"}


def load_keys() -> list[str]:
    keys: list[str] = []
    for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("DATA_GOV_IN_API_KEY"):
            keys += KEY_RE.findall(line.split("=", 1)[1])
    return list(dict.fromkeys(keys))


_KEYS = load_keys()
_ROTATION = cycle(_KEYS)
_LOCK = Lock()


def key_count() -> int:
    return len(_KEYS)


def _next_key() -> str:
    with _LOCK:
        return next(_ROTATION)


def _clean(message: str) -> str:
    for key in _KEYS:
        message = message.replace(key, "<KEY>")
    return message


def get(path: str, params: dict, timeout: int = 60, retries: int = 4) -> dict:
    """GET {BASE}/{path} with a rotating key. Raises RuntimeError (key removed from the message) on failure."""
    last = ""
    for attempt in range(1, retries + 1):
        query = urllib.parse.urlencode({**params, "api-key": _next_key(), "format": "json"})
        request = urllib.request.Request(f"{BASE}/{path}?{query}", headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code in (401, 403):
                time.sleep(1)  # try the next key
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, http.client.HTTPException, ConnectionError) as exc:
            last = _clean(str(exc))[:120]
        time.sleep(2 * attempt)
    raise RuntimeError(f"{path}: {last}")


def catalog(title: str, limit: int = 20, offset: int = 0) -> list[dict]:
    # fields= keeps the response small (without it the catalog sends tens of MB per query)
    data = get("lists", {"limit": limit, "offset": offset, "filters[title]": title, "fields": "index_name,title"})
    return data.get("records", [])


def fetch_pages(resource_id: str, filters: dict | None = None, page: int = 1000, max_records: int | None = None) -> list[dict]:
    """Download all records of a resource, one thread per key."""
    base = {f"filters[{k}]": v for k, v in (filters or {}).items()}
    first = get(f"resource/{resource_id}", {**base, "limit": 1})
    total = int(first.get("total", 0))
    if max_records:
        total = min(total, max_records)
    offsets = list(range(0, total, page))
    workers = max(1, min(len(_KEYS), 4))

    def one(offset: int) -> list[dict]:
        return get(f"resource/{resource_id}", {**base, "limit": page, "offset": offset}, timeout=120).get("records", [])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        chunks = list(pool.map(one, offsets))
    return [row for chunk in chunks for row in chunk]
