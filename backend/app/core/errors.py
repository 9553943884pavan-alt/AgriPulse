"""Typed error helpers for all non-2xx responses (backend/SPECS.md §5.1).

Usage:
    raise AppError("LOCATION_NOT_FOUND", {"location": "Foobar"})
"""

from __future__ import annotations

from fastapi import HTTPException

from app.schemas import ErrorCode, ErrorDetail, ErrorResponse

# ── HTTP status map ───────────────────────────────────────────────────────────
_STATUS: dict[str, int] = {
    "VALIDATION_ERROR": 422,
    "LOCATION_NOT_FOUND": 422,
    "DISTRICT_NOT_AGRICULTURAL": 422,
    "PLAN_NOT_FOUND": 404,
    "AUDIO_TOO_LARGE": 413,
    "STT_FAILED": 502,
    "UPSTREAM_UNAVAILABLE": 503,
    "RATE_LIMITED": 429,
    "INTERNAL": 500,
}

# ── User-facing messages in all three languages ───────────────────────────────
_USER_MSG: dict[str, dict[str, str]] = {
    "VALIDATION_ERROR": {
        "mr": "दिलेली माहिती अपूर्ण किंवा चुकीची आहे.",
        "hi": "दी गई जानकारी अधूरी या गलत है।",
        "en": "The information provided is incomplete or invalid.",
    },
    "LOCATION_NOT_FOUND": {
        "mr": "हे ठिकाण भारतात सापडले नाही.",
        "hi": "यह स्थान भारत में नहीं मिला।",
        "en": "We could not find this place in India.",
    },
    "DISTRICT_NOT_AGRICULTURAL": {
        "mr": "या जिल्ह्यात शेती नोंदी नाहीत (मुंबई शहर / उपनगर).",
        "hi": "इस जिले में कृषि रिकॉर्ड नहीं हैं (मुंबई शहर / उपनगर)।",
        "en": "No crop statistics exist for this district (Mumbai City / Suburban).",
    },
    "PLAN_NOT_FOUND": {
        "mr": "हा प्लॅन आढळला नाही किंवा मुदत संपली.",
        "hi": "यह प्लान नहीं मिला या समय समाप्त हो गया।",
        "en": "Plan not found or expired.",
    },
    "AUDIO_TOO_LARGE": {
        "mr": "ऑडिओ फाइल खूप मोठी आहे (जास्तीत जास्त 10 MB, 60 सेकंद).",
        "hi": "ऑडियो फ़ाइल बहुत बड़ी है (अधिकतम 10 MB, 60 सेकंड)।",
        "en": "Audio too large (max 10 MB, 60 seconds).",
    },
    "STT_FAILED": {
        "mr": "बोलणे ओळखता आले नाही. कृपया पुन्हा बोला किंवा टाइप करा.",
        "hi": "भाषण पहचानने में विफल। कृपया फिर से बोलें या टाइप करें।",
        "en": "Speech recognition failed. Please try again or type your message.",
    },
    "UPSTREAM_UNAVAILABLE": {
        "mr": "बाह्य सेवा सध्या उपलब्ध नाही. जुना डेटा वापरत आहोत.",
        "hi": "बाहरी सेवा अभी उपलब्ध नहीं है। पुराना डेटा उपयोग हो रहा है।",
        "en": "External service unavailable. Using cached data where possible.",
    },
    "RATE_LIMITED": {
        "mr": "खूप जास्त विनंत्या. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
        "hi": "बहुत अधिक अनुरोध। कृपया कुछ देर बाद फिर प्रयास करें।",
        "en": "Too many requests. Please try again in a moment.",
    },
    "INTERNAL": {
        "mr": "अनपेक्षित त्रुटी. कृपया पुन्हा प्रयत्न करा.",
        "hi": "अप्रत्याशित त्रुटि। कृपया पुनः प्रयास करें।",
        "en": "An unexpected error occurred. Please try again.",
    },
}

_RETRYABLE: set[str] = {"UPSTREAM_UNAVAILABLE", "RATE_LIMITED", "STT_FAILED", "INTERNAL"}


class AppError(Exception):
    """Raise this anywhere in the app; the FastAPI exception handler converts it."""

    def __init__(
        self,
        code: ErrorCode,
        details: dict | None = None,
        message: str | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.message = message or _USER_MSG[code]["en"]
        self.status_code = _STATUS[code]
        super().__init__(self.message)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                user_message=_USER_MSG[self.code],
                retryable=self.code in _RETRYABLE,
                details=self.details,
            )
        )

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail=self.to_response().model_dump(),
        )
