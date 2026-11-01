"""SVC.9 — Speech service (Sarvam STT + TTS).

Accepted audio formats for STT: webm/ogg/wav/mp3/mp4
  audio/mp4 is required for iOS Safari — MediaRecorder on iOS only produces
  audio/mp4; judges on iPhones must not lose mic access.

Fallbacks:
  STT: return None → frontend asks farmer to type
  TTS: raise AppError("UPSTREAM_UNAVAILABLE") → frontend uses browser speechSynthesis
"""

from __future__ import annotations

import io
import logging

import av
import httpx

from app.config import settings
from app.core.errors import AppError

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
    "audio/aac",
    "audio/mp4",       # iOS Safari MediaRecorder
    "audio/x-m4a",    # iOS alternative
    "video/mp4",       # some iOS streams as video/mp4
}
MAX_AUDIO_BYTES = 10 * 1024 * 1024   # 10 MB
MAX_AUDIO_SECONDS = 30
MAX_TTS_CHARACTERS = 2500

_TTS_SPEAKERS = {
    "mr": "ishita_mr_conversational",
    "hi": "simran_hi_conversation",
    "en": "simran_en_conversation",
}


_STT_LANG = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN"}
_EXT_BY_TYPE = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/mp3": "mp3",
    "audio/mpeg": "mp3",
    "audio/aac": "aac",
    "audio/mp4": "mp4",
    "audio/x-m4a": "m4a",
    "video/mp4": "mp4",
}


def _stt_filename(content_type: str) -> str:
    """Sarvam detects the audio container from the file extension (a bare 'audio'
    name is rejected with HTTP 400), so name the part after its MIME type."""
    return f"audio.{_EXT_BY_TYPE.get(content_type.split(';')[0].strip().lower(), 'wav')}"


def _tts_speaker(language: str) -> str:
    return _TTS_SPEAKERS.get(language, _TTS_SPEAKERS["mr"])


def _sarvam_headers() -> dict:
    return {"api-subscription-key": settings.SARVAM_API_KEY}


def _validate_audio_duration(audio_bytes: bytes) -> float:
    """Return the media duration, rejecting unreadable or over-limit audio."""
    try:
        with av.open(io.BytesIO(audio_bytes)) as container:
            audio_stream = next(iter(container.streams.audio), None)
            if audio_stream is None:
                raise ValueError("No audio stream")
            if audio_stream.duration is not None and audio_stream.time_base is not None:
                duration = float(audio_stream.duration * audio_stream.time_base)
            elif container.duration is not None:
                duration = float(container.duration / av.time_base)
            else:
                duration = sum(
                    frame.samples / frame.sample_rate
                    for frame in container.decode(audio_stream)
                    if frame.sample_rate
                )
    except Exception as exc:
        raise AppError(
            "VALIDATION_ERROR",
            {"field": "audio", "reason": "duration_unavailable"},
        ) from exc

    if duration > MAX_AUDIO_SECONDS:
        raise AppError(
            "VALIDATION_ERROR",
            {
                "field": "audio",
                "max_duration_seconds": MAX_AUDIO_SECONDS,
                "duration_seconds": round(duration, 2),
            },
        )
    return duration


async def transcribe(audio_bytes: bytes, content_type: str, language_hint: str | None = None) -> dict:
    """Convert audio to text using Sarvam STT.

    Returns: {"text": str, "language": str, "duration_s": float, "provider": str}
    Returns {"text": None, "error": str} if all providers fail.
    """
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise AppError("AUDIO_TOO_LARGE", {"size_bytes": len(audio_bytes)})
    duration_seconds = _validate_audio_duration(audio_bytes)

    if not settings.SARVAM_API_KEY:
        logger.warning("SARVAM_API_KEY not set; STT unavailable")
        return {"text": None, "error": "STT service not configured"}

    # STT uses only SARVAM_STT_MODEL — do NOT iterate sarvam_fallback_list
    # (those are chat model IDs, not STT model IDs).
    stt_model = settings.SARVAM_STT_MODEL or "saaras:v4"
    models = [stt_model]

    for model in models:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                # NOTE: do NOT send 'mode' — it is only valid for saaras:v3.
                # saaras:v4 ignores it and some versions return 400.
                form_data: dict = {
                    "model": model,
                    "language_code": _STT_LANG.get(language_hint or "", "unknown"),
                }
                resp = await client.post(
                    _STT_URL,
                    headers=_sarvam_headers(),
                    files={"file": (_stt_filename(content_type), audio_bytes, content_type)},
                    data=form_data,
                )
                resp.raise_for_status()
            data = resp.json()
            transcript = data.get("transcript", "")
            if not isinstance(transcript, str) or not transcript.strip():
                # A successful HTTP response with no words means the recorder
                # captured silence (usually a muted or wrong input device).
                raise AppError(
                    "STT_FAILED",
                    {"reason": "empty_transcript"},
                    message="No speech was detected from the selected microphone.",
                    user_message={
                        "en": "No speech was detected. Check the selected microphone, then try again.",
                        "mr": "निवडलेल्या मायक्रोफोनमधून आवाज मिळाला नाही. मायक्रोफोन तपासून पुन्हा प्रयत्न करा.",
                        "hi": "चुने गए माइक्रोफ़ोन से आवाज़ नहीं मिली। माइक्रोफ़ोन जाँचकर फिर कोशिश करें।",
                    },
                )
            return {
                "text": transcript,
                "language": (data.get("language_code") or language_hint or "mr")[:2],
                "duration_s": duration_seconds,
                "provider": "sarvam",
            }
        except AppError:
            raise
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
    if len(text) > MAX_TTS_CHARACTERS:
        raise AppError("VALIDATION_ERROR", {"field": "text", "max_characters": MAX_TTS_CHARACTERS})

    lang_code = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN"}.get(language, "mr-IN")
    # TTS uses only SARVAM_TTS_MODEL — do NOT iterate sarvam_fallback_list
    # (those are chat model IDs, not TTS model IDs).
    tts_model = settings.SARVAM_TTS_MODEL or "bulbul:v4-flash"
    models = [tts_model]

    for model in models:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _TTS_URL,
                    headers=_sarvam_headers(),
                    json={
                        "text": text,
                        "language_code": lang_code,   # NOT target_language_code
                        "speaker": _tts_speaker(language),
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
