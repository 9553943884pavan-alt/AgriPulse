"""SVC.9 — Speech service (Sarvam STT + TTS).

Accepted audio formats for STT: webm/ogg/wav/mp3/mp4
  audio/mp4 is required for iOS Safari — MediaRecorder on iOS only produces
  audio/mp4; judges on iPhones must not lose mic access.

Fallbacks:
  STT: return None → frontend asks farmer to type
  TTS: raise AppError("UPSTREAM_UNAVAILABLE") → frontend uses browser speechSynthesis
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.core.errors import AppError
from app.core.http_client import post_json

logger = logging.getLogger(__name__)

_SARVAM_BASE = "https://api.sarvam.ai"
_STT_URL = f"{_SARVAM_BASE}/speech-to-text"
_TTS_URL = f"{_SARVAM_BASE}/text-to-speech"
_TIMEOUT = httpx.Timeout(connect=10.0, read=10.0, write=10.0, pool=2.0)

ACCEPTED_AUDIO_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/mp3",
    "audio/mpeg",
    "audio/mp4",       # iOS Safari MediaRecorder
    "audio/x-m4a",    # iOS alternative
    "video/mp4",       # some iOS streams as video/mp4
}
MAX_AUDIO_BYTES = 10 * 1024 * 1024   # 10 MB
MAX_AUDIO_SECONDS = 60


def _sarvam_headers() -> dict:
    return {"api-subscription-key": settings.SARVAM_API_KEY}


async def transcribe(audio_bytes: bytes, content_type: str, language_hint: str | None = None) -> dict:
    """Convert audio to text using Sarvam STT.

    Returns: {"text": str, "language": str, "duration_s": float, "provider": str}
    Returns {"text": None, "error": str} if all providers fail.
    """
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise AppError("AUDIO_TOO_LARGE", {"size_bytes": len(audio_bytes)})

    if not settings.SARVAM_API_KEY:
        logger.warning("SARVAM_API_KEY not set; STT unavailable")
        return {"text": None, "error": "STT service not configured"}

    # Try primary model, then fallbacks
    models = [settings.SARVAM_STT_MODEL] + settings.sarvam_fallback_list
    models = [m for m in models if m]  # remove empty

    for model in models:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _STT_URL,
                    headers=_sarvam_headers(),
                    files={"file": ("audio", audio_bytes, content_type)},
                    data={
                        "model": model,
                        "language_code": language_hint or "unknown",
                        "mode": "transcribe",
                    },
                )
                resp.raise_for_status()
            data = resp.json()
            return {
                "text": data.get("transcript", ""),
                "language": (data.get("language_code") or language_hint or "mr")[:2],
                "duration_s": 0.0,
                "provider": "sarvam",
            }
        except Exception as exc:
            logger.warning("Sarvam STT model %s failed: %s", model, exc)

    logger.error("All Sarvam STT models failed")
    raise AppError("STT_FAILED")


async def speak(text: str, language: str = "mr", speed: float = 1.0) -> bytes:
    """Convert text to audio using Sarvam TTS.

    Returns audio/wav bytes.
    Raises AppError("UPSTREAM_UNAVAILABLE") if all providers fail.
    """
    if not settings.SARVAM_API_KEY:
        raise AppError("UPSTREAM_UNAVAILABLE", {"service": "TTS", "reason": "SARVAM_API_KEY not set"})

    lang_code = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN"}.get(language, "mr-IN")
    models = [settings.SARVAM_TTS_MODEL] + settings.sarvam_fallback_list
    models = [m for m in models if m]

    for model in models:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _TTS_URL,
                    headers=_sarvam_headers(),
                    json={
                        "text": text,
                        "target_language_code": lang_code,
                        "speaker": "meera" if lang_code == "mr-IN" else "shubh",
                        "pace": speed,
                        "model": model,
                        "speech_sample_rate": 22050,
                    },
                )
                resp.raise_for_status()
            import base64
            audios = resp.json().get("audios", [])
            if audios:
                return base64.b64decode(audios[0])
        except Exception as exc:
            logger.warning("Sarvam TTS model %s failed: %s", model, exc)

    raise AppError("UPSTREAM_UNAVAILABLE", {"service": "TTS"})
