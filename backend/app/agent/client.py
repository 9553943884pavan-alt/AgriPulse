"""AG.1 — Sarvam AI chat client with model fallback.

Scope: chat completions ONLY.
STT and TTS remain in app/services/speech.py.
Do NOT add STT/TTS here — it would duplicate the service layer.

STT/TTS contract note (for callers of speech.py):
  Forward content_type verbatim as the multipart part's Content-Type.
  NEVER hardcode "audio/webm".
  Accepted MIME types: audio/webm · audio/ogg · audio/wav · audio/mpeg · audio/mp4
  iOS Safari (MediaRecorder) produces audio/mp4; hardcoding webm breaks iPhones.

Chat endpoint: POST https://api.sarvam.ai/v2/chat/completions
Auth header:   api-subscription-key: <SARVAM_API_KEY>
Model order:   SARVAM_CHAT_MODEL → each model in SARVAM_FALLBACK_MODELS
Per-model timeout: 12 s, total budget 20 s
On 5xx or timeout: try next model immediately
On 429: backoff (1 s, 2 s), max 2 retries per model; empty content => next model
All models failed: raise SarvamAllModelsFailed — caller uses template answer
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SARVAM_CHAT_URL = "https://api.sarvam.ai/v2/chat/completions"

# Whole chat() call (all models, all retries) must finish inside this budget so
# the farmer never waits more than ~20 s for one LLM step.
TOTAL_BUDGET_S = 20.0
PER_MODEL_TIMEOUT_S = 12.0
MAX_429_RETRIES = 2

# Sarvam reasoning models (sarvam-105b) otherwise burn the whole token budget on
# hidden "thinking" and return EMPTY content (finish_reason=length), ~15 s per
# try. `reasoning_effort="low"` does not stop that, and "none" is rejected by
# some models. `chat_template_kwargs.enable_thinking=false` is accepted by all
# configured models and gives a real answer in ~2 s (verified live).
_NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}


class SarvamAllModelsFailed(Exception):
    """Raised when every Sarvam chat model has been tried and all failed."""


def _content_of(data: dict) -> str:
    try:
        return (data["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


class SarvamClient:
    """Stateless client — safe to instantiate once and reuse across requests."""

    def __init__(self) -> None:
        self._headers = {
            "api-subscription-key": settings.SARVAM_API_KEY,
            "Content-Type": "application/json",
        }

    def _model_order(self) -> list[str]:
        """Primary model first, then fallbacks. Empty strings and duplicates are skipped."""
        models = [settings.SARVAM_CHAT_MODEL] + settings.sarvam_fallback_list
        seen: list[str] = []
        for m in models:
            if m and m not in seen:
                seen.append(m)
        return seen

    async def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> dict:
        """Try each model in order. Returns the full OpenAI-compatible response dict.

        A response with EMPTY content (or finish_reason=length with no content)
        counts as a failure for that model and the next model is tried at once.

        Raises SarvamAllModelsFailed when every model is exhausted or the total
        time budget runs out. Callers then use their template / regex fallback.
        """
        if not settings.SARVAM_API_KEY:
            raise SarvamAllModelsFailed("SARVAM_API_KEY not set")

        deadline = time.monotonic() + TOTAL_BUDGET_S
        last_exc: Exception | str | None = None
        for model in self._model_order():
            use_extras = True
            rate_limited = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining < 1.5:
                    raise SarvamAllModelsFailed(
                        f"Sarvam time budget exhausted. Last error: {last_exc}"
                    )
                payload: dict = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if use_extras:
                    payload.update(_NO_THINKING)
                if response_format:
                    payload["response_format"] = response_format
                try:
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(min(PER_MODEL_TIMEOUT_S, remaining))
                    ) as client:
                        resp = await client.post(
                            SARVAM_CHAT_URL, headers=self._headers, json=payload
                        )
                except httpx.TimeoutException as exc:
                    logger.warning("Sarvam timeout (model=%s)", model)
                    last_exc = exc
                    break  # next model
                except Exception as exc:
                    logger.warning("Sarvam network error (model=%s): %s", model, exc)
                    last_exc = exc
                    break

                if resp.status_code == 429 and rate_limited < MAX_429_RETRIES:
                    wait = 2 ** rate_limited
                    rate_limited += 1
                    logger.warning("Sarvam rate-limited (model=%s); sleeping %ds", model, wait)
                    await asyncio.sleep(min(wait, max(0.0, deadline - time.monotonic() - 1.5)))
                    continue
                if resp.status_code == 400 and use_extras:
                    # Model rejected the thinking switch: retry once without it.
                    use_extras = False
                    continue
                if resp.status_code != 200:
                    logger.warning("Sarvam HTTP %d (model=%s)", resp.status_code, model)
                    last_exc = f"HTTP {resp.status_code}"
                    break

                try:
                    data = resp.json()
                except ValueError as exc:
                    last_exc = exc
                    break
                if not _content_of(data):
                    logger.warning("Sarvam empty content (model=%s); trying next model", model)
                    last_exc = f"empty content from {model}"
                    break
                return data

        raise SarvamAllModelsFailed(
            f"All Sarvam chat models failed. Last error: {last_exc}"
        )

    def extract_text(self, response: dict) -> str:
        """Pull the assistant message text from an OpenAI-compatible response."""
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Unexpected Sarvam response shape: {response}") from exc


# Module-level singleton — one client per process
_client: SarvamClient | None = None


def get_sarvam_client() -> SarvamClient:
    global _client
    if _client is None:
        _client = SarvamClient()
    return _client
