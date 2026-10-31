"""AG.7 — LangGraph AsyncSqliteSaver checkpointer setup + E3 write-back helper.

LangGraph 0.2 requires AsyncSqliteSaver for async graphs.
SqliteSaver (sync) deadlocks when called from async code — do not use it.

Correct import:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  ← use this
    NOT: from langgraph.checkpoint.sqlite import SqliteSaver       ← sync, wrong

The checkpointer manages its own tables inside settings.CACHE_DB_PATH.
LangGraph state is keyed by thread_id via config["configurable"]["thread_id"].

E3 write-back: update_profile_fields() is the ONLY place outside the graph
that may write to the checkpointer. Called from backend/app/api/plan.py
after a successful reoptimize, so the next chat turn reads the updated profile.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def get_checkpointer():
    """Return a MemorySaver for the graph checkpointer.

    MemorySaver is LangGraph's built-in in-process checkpointer — no threading
    issues, no external dependencies. It keeps state for the lifetime of the
    Python process (survives across requests in the same server process).

    For persistent cross-restart memory, the agent also writes to the SQLite
    agent_memory table via app/core/cache.py, which is the safe shared store.
    AsyncSqliteSaver has thread-restart constraints in Python 3.13 that make
    it unreliable as a compiled-graph checkpointer in the current version.
    """
    try:
        from langgraph.checkpoint.memory import MemorySaver  # type: ignore[import]
        return MemorySaver()
    except ImportError:
        logger.warning("MemorySaver not found — running without checkpointer")
        return None


async def update_profile_fields(thread_id: str, patch: dict) -> None:
    """E3 reoptimize write-back.

    When the farmer moves the risk slider or changes budget/land via E3:
      1. E3 re-optimizes with the new value (fast, no external API calls).
      2. E3 calls THIS function to patch the LangGraph checkpointer.
      3. The NEXT chat turn reads the updated profile from memory.

    Without this, E3 changes risk to "safe" but the next follow-up question
    starts from the old "balanced" risk because the checkpointer was never updated.

    This is the ONLY place outside the graph allowed to write to the checkpointer.
    """
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # type: ignore[import]
    except ImportError:
        logger.warning("update_profile_fields: AsyncSqliteSaver not available — skipping write-back")
        return

    try:
        async with AsyncSqliteSaver.from_conn_string(settings.CACHE_DB_PATH) as saver:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint = await saver.aget(config)
            if checkpoint is None:
                logger.warning("update_profile_fields: no checkpoint for thread_id=%s", thread_id)
                return

            # Deep-merge the patch into the profile field of the checkpoint state
            state = checkpoint.get("channel_values", {})
            profile_data: dict = {}
            if "profile" in state:
                p = state["profile"]
                profile_data = p.model_dump(mode="json") if hasattr(p, "model_dump") else dict(p)
            profile_data.update(patch)
            state["profile"] = profile_data

            # Write back — preserve metadata, only update channel_values
            new_checkpoint = {**checkpoint, "channel_values": state}
            await saver.aput(config, new_checkpoint, {})
            logger.info("update_profile_fields: wrote patch %s to thread %s", list(patch.keys()), thread_id)

    except Exception as exc:
        # Never crash E3 because of a memory write failure
        logger.warning("update_profile_fields failed (thread=%s): %s", thread_id, exc)
