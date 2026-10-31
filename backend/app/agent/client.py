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
Per-model timeout: 15 s
On 5xx or timeout: try next model immediately
On 429: exponential backoff (1 s, 2 s, 4 s), max 3 retries per model
All models failed: raise SarvamAllModelsFailed — caller uses template answer
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SARVAM_CHAT_URL = "https://api.sarvam.ai/v2/chat/completions"
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=2.0)


class SarvamAllModelsFailed(Exception):
    """Raised when every Sarvam chat model has been tried and all failed."""


class SarvamClient:
    """Stateless client — safe to instantiate once and reuse across requests."""

    def __init__(self) -> None:
        self._headers = {
            "api-subscription-key": settings.SARVAM_API_KEY,
            "Content-Type": "application/json",
        }

    def _model_order(self) -> list[str]:
        """Primary model first, then fallbacks. Empty strings are skipped."""
        models = [settings.SARVAM_CHAT_MODEL] + settings.sarvam_fallback_list
        return [m for m in models if m]

    async def chat(
        self,
        messages: list[dict],
        response_format: dict | None = None,
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> dict:
        """Try each model in order. Returns the full OpenAI-compatible response dict.

        response_format examples:
          {"type": "json_object"}                         — valid JSON guaranteed
          {"type": "json_schema", "json_schema": {...}}   — structured output (sarvam-105b)

        Raises SarvamAllModelsFailed when every model and every retry is exhausted.
        """
        last_exc: Exception | None = None
        for model in self._model_order():
            for attempt in range(3):
                try:
                    payload: dict = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if response_format:
                        payload["response_format"] = response_format

                    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                        resp = await client.post(
                            SARVAM_CHAT_URL,
                            headers=self._headers,
                            json=payload,
                        )

                    if resp.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning(
                            "Sarvam rate-limited (model=%s attempt=%d); sleeping %ds",
                            model, attempt, wait,
                        )
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    return resp.json()

                except httpx.TimeoutException as exc:
                    logger.warning(
                        "Sarvam timeout (model=%s attempt=%d): %s", model, attempt, exc
                    )
                    last_exc = exc
                    break   # timeout → skip remaining retries, try next model

                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "Sarvam HTTP %d (model=%s attempt=%d)",
                        exc.response.status_code, model, attempt,
                    )
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)

                except Exception as exc:
                    logger.warning(
                        "Sarvam unexpected error (model=%s attempt=%d): %s",
                        model, attempt, exc,
                    )
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)

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
