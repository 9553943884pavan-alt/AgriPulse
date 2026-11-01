"""E5  POST /api/transcribe
E6  POST /api/speak
"""

from __future__ import annotations

import math

from fastapi import APIRouter, File, Form, Response, UploadFile

from app.core.errors import AppError
from app.services.speech import (
    ACCEPTED_AUDIO_TYPES,
    MAX_AUDIO_BYTES,
    MAX_TTS_CHARACTERS,
    speak,
    transcribe,
)

router = APIRouter()


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language_hint: str | None = Form(None),
) -> dict:
    """E5 — Audio → text + detected language (F1 mic button).

    Accepted: webm/ogg/wav/mp3/mp4 (mp4 required for iOS Safari).
    Max size: 10 MB, max duration: 30 s (Sarvam Saaras v4 limit).
    """
    content_type = audio.content_type or ""
    # Strip codec suffix (e.g. "audio/webm;codecs=opus" → "audio/webm")
    ct_base = content_type.split(";")[0].strip().lower()
    if ct_base not in ACCEPTED_AUDIO_TYPES:
        raise AppError(
            "VALIDATION_ERROR",
            {"content_type": content_type, "accepted": list(ACCEPTED_AUDIO_TYPES)},
        )

    # Read only one byte beyond the limit. UploadFile.read() without a size
    # buffers the entire multipart body before the size check.
    audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise AppError("AUDIO_TOO_LARGE", {"size_bytes": len(audio_bytes)})

    result = await transcribe(audio_bytes, ct_base, language_hint)
    if result.get("text") is None:
        raise AppError("STT_FAILED")
    return result


@router.post("/speak")
async def speak_text(body: dict) -> Response:
    """E6 — Text → audio/wav (F10 spoken reply).

    Returns audio/wav bytes, or 503 if Sarvam is unavailable
    (frontend falls back to browser speechSynthesis).
    """
    text = body.get("text", "")
    language = body.get("language", "mr")
    if not isinstance(text, str) or not text:
        raise AppError("VALIDATION_ERROR", {"field": "text"})
    if len(text) > MAX_TTS_CHARACTERS:
        raise AppError(
            "VALIDATION_ERROR",
            {"field": "text", "max_characters": MAX_TTS_CHARACTERS},
        )
    raw_speed = body.get("speed", 1.0)
    try:
        # bool is technically a float subclass, but is never a useful speech pace.
        if isinstance(raw_speed, bool):
            raise ValueError
        speed = float(raw_speed)
    except (TypeError, ValueError):
        raise AppError("VALIDATION_ERROR", {"field": "speed"}) from None
    if not math.isfinite(speed) or speed <= 0:
        raise AppError("VALIDATION_ERROR", {"field": "speed"})
    audio_bytes = await speak(text, language, speed)
    return Response(content=audio_bytes, media_type="audio/wav")
