"""Async httpx singleton with per-call timeout and retry with exponential backoff.

All outgoing HTTP calls go through `get_client()`. Never use requests or urllib
directly in services — only this client, so timeouts and retries are uniform.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

# Default timeouts (seconds) — each service may override per the SPECS table
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=2.0)

# Headers sent with every request
_BASE_HEADERS = {"User-Agent": "AgriPulse-backend/0.1 (github.com/agripulse)"}


def get_client() -> httpx.AsyncClient:
    """Return the shared async httpx client (created on first call)."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers=_BASE_HEADERS,
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def fetch(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: httpx.Timeout | None = None,
    retries: int = 2,
    backoff: float = 2.0,
) -> httpx.Response:
    """GET with retry and exponential backoff.

    Raises httpx.HTTPStatusError on a non-2xx after all retries are exhausted.
    The caller is responsible for caching the response before re-raising.
    """
    client = get_client()
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await client.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout or DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
            return response
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt < retries:
                wait = backoff ** attempt
                logger.warning(
                    "fetch %s attempt %d/%d failed (%s); retrying in %.1fs",
                    url, attempt + 1, retries + 1, exc, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("fetch %s failed after %d attempts: %s", url, retries + 1, exc)
    raise last_exc  # type: ignore[misc]


async def post_json(
    url: str,
    *,
    json: dict | None = None,
    data: dict | None = None,
    headers: dict | None = None,
    timeout: httpx.Timeout | None = None,
) -> httpx.Response:
    """POST JSON with no retry (idempotency not guaranteed)."""
    client = get_client()
    response = await client.post(
        url,
        json=json,
        data=data,
        headers=headers,
        timeout=timeout or DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    return response
