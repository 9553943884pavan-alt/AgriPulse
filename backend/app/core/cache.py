"""Three-table SQLite cache + in-memory TTL layer (backend/SPECS.md §4.3).

Tables:
  upstream_cache  — real API / file responses only (TTL per data type)
  plans           — generated PlanResult inputs, 24 h
  agent_memory    — LangGraph checkpointer data (no TTL; managed by LangGraph)

The "never store anything that did not come from a real API or file" rule
applies to upstream_cache only. Plans and agent_memory are generated data
and are clearly separated.

Usage:
    cache = await get_cache()
    raw = await cache.get_upstream("weather:Beed")
    if raw is None:
        raw = await fetch_live(...)
        await cache.set_upstream("weather:Beed", raw, ttl=TTL_WEATHER)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import aiosqlite

from app.config import settings

logger = logging.getLogger(__name__)

# ── TTL constants (seconds) ───────────────────────────────────────────────────
TTL_GEOCODING = 7 * 24 * 3600          # 7 days
TTL_WEATHER = 6 * 3600                 # 6 hours
TTL_PRICES = 6 * 3600                  # 6 hours
TTL_SOIL = 30 * 24 * 3600              # 30 days
TTL_PLAN = 24 * 3600                   # 24 hours

_DDL = """
CREATE TABLE IF NOT EXISTS upstream_cache (
    key      TEXT PRIMARY KEY,
    value    TEXT NOT NULL,
    stored   REAL NOT NULL,
    ttl      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    plan_id  TEXT PRIMARY KEY,
    value    TEXT NOT NULL,
    stored   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_memory (
    thread_id TEXT NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT NOT NULL,
    stored    REAL NOT NULL,
    PRIMARY KEY (thread_id, key)
);
"""

_db: aiosqlite.Connection | None = None


async def _get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        path = Path(settings.CACHE_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(path))
        _db.row_factory = aiosqlite.Row
        await _db.executescript(_DDL)
        await _db.commit()
    return _db


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


class Cache:
    # ── upstream_cache ────────────────────────────────────────────────────────

    async def get_upstream(self, key: str) -> dict | None:
        """Return the cached value if fresh; None if missing or expired."""
        db = await _get_db()
        async with db.execute(
            "SELECT value, stored, ttl FROM upstream_cache WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if time.time() - row["stored"] > row["ttl"]:
            logger.debug("cache expired: %s", key)
            return None
        return json.loads(row["value"])

    async def get_upstream_stale(self, key: str) -> dict | None:
        """Return whatever is cached, even if expired (stale fallback)."""
        db = await _get_db()
        async with db.execute(
            "SELECT value FROM upstream_cache WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return json.loads(row["value"]) if row else None

    async def set_upstream(self, key: str, value: dict, ttl: float) -> None:
        db = await _get_db()
        await db.execute(
            "INSERT OR REPLACE INTO upstream_cache (key, value, stored, ttl) VALUES (?,?,?,?)",
            (key, json.dumps(value), time.time(), ttl),
        )
        await db.commit()

    # ── plans ─────────────────────────────────────────────────────────────────

    async def get_plan(self, plan_id: str) -> dict | None:
        db = await _get_db()
        async with db.execute(
            "SELECT value, stored FROM plans WHERE plan_id = ?", (plan_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if time.time() - row["stored"] > TTL_PLAN:
            return None
        return json.loads(row["value"])

    async def set_plan(self, plan_id: str, value: dict) -> None:
        db = await _get_db()
        await db.execute(
            "INSERT OR REPLACE INTO plans (plan_id, value, stored) VALUES (?,?,?)",
            (plan_id, json.dumps(value), time.time()),
        )
        await db.commit()

    # ── agent_memory ──────────────────────────────────────────────────────────

    async def get_memory(self, thread_id: str, key: str) -> dict | None:
        db = await _get_db()
        async with db.execute(
            "SELECT value FROM agent_memory WHERE thread_id = ? AND key = ?",
            (thread_id, key),
        ) as cur:
            row = await cur.fetchone()
        return json.loads(row["value"]) if row else None

    async def set_memory(self, thread_id: str, key: str, value: dict) -> None:
        db = await _get_db()
        await db.execute(
            "INSERT OR REPLACE INTO agent_memory (thread_id, key, value, stored) VALUES (?,?,?,?)",
            (thread_id, key, json.dumps(value), time.time()),
        )
        await db.commit()

    async def get_all_memory(self, thread_id: str) -> dict[str, dict]:
        db = await _get_db()
        result = {}
        async with db.execute(
            "SELECT key, value FROM agent_memory WHERE thread_id = ?", (thread_id,)
        ) as cur:
            async for row in cur:
                result[row["key"]] = json.loads(row["value"])
        return result


_cache_instance: Cache | None = None


async def get_cache() -> Cache:
    global _cache_instance
    if _cache_instance is None:
        await _get_db()   # ensures DB is initialised
        _cache_instance = Cache()
    return _cache_instance
