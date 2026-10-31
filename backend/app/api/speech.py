"""E5  POST /api/transcribe
E6  POST /api/speak
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Response, UploadFile

from app.core.errors import AppError
from app.services.speech import (
    ACCEPTED_AUDIO_TYPES,
    MAX_AUDIO_BYTES,
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
    Max size: 10 MB, max duration: 60 s.
    """
    content_type = audio.content_type or ""
    # Strip codec suffix (e.g. "audio/webm;codecs=opus" → "audio/webm")
    ct_base = content_type.split(";")[0].strip().lower()
    if ct_base not in ACCEPTED_AUDIO_TYPES:
        raise AppError(
            "VALIDATION_ERROR",
            {"content_type": content_type, "accepted": list(ACCEPTED_AUDIO_TYPES)},
        ).to_http_exception()

    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise AppError("AUDIO_TOO_LARGE", {"size_bytes": len(audio_bytes)}).to_http_exception()

    try:
        result = await transcribe(audio_bytes, ct_base, language_hint)
        if result.get("text") is None:
            raise AppError("STT_FAILED")
        return result
    except AppError as e:
        raise e.to_http_exception()


@router.post("/speak")
async def speak_text(body: dict) -> Response:
    """E6 — Text → audio/wav (F10 spoken reply).

    Returns audio/wav bytes, or 503 if Sarvam is unavailable
    (frontend falls back to browser speechSynthesis).
    """
    text = body.get("text", "")
    language = body.get("language", "mr")
    speed = float(body.get("speed", 1.0))
    if not text:
        raise AppError("VALIDATION_ERROR", {"field": "text"}).to_http_exception()
    try:
        audio_bytes = await speak(text, language, speed)
        return Response(content=audio_bytes, media_type="audio/wav")
    except AppError as e:
        raise e.to_http_exception()
