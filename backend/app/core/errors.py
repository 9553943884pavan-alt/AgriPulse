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
    "PROFILE_STALE": 409,
    "RUN_IN_PROGRESS": 409,
    "NO_SAVED_PROFILE": 422,
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
    "PROFILE_STALE": {
        "mr": "तुमचे शेत प्रोफाइल बदलले आहे. कृपया नवीनतम प्रोफाइल लोड करून पुन्हा प्रयत्न करा.",
        "hi": "आपकी खेत प्रोफ़ाइल बदल गई है। कृपया नवीनतम प्रोफ़ाइल लोड करके फिर प्रयास करें।",
        "en": "Your farm profile has changed. Please reload the latest profile and try again.",
    },
    "RUN_IN_PROGRESS": {
        "mr": "या संभाषणासाठी प्लॅन आधीच तयार होत आहे. कृपया तो पूर्ण होण्याची वाट पहा.",
        "hi": "इस बातचीत के लिए प्लान पहले से बन रहा है। कृपया उसके पूरा होने का इंतज़ार करें।",
        "en": "A plan is already being prepared for this conversation. Please wait for it to finish.",
    },
    "NO_SAVED_PROFILE": {
        "mr": "प्लॅन तयार करण्यासाठी आधी तुमचे शेत प्रोफाइल सेव्ह करा.",
        "hi": "प्लान बनाने से पहले अपनी खेत प्रोफ़ाइल सेव करें।",
        "en": "Please save your farm profile before optimizing a plan.",
    },
    "AUDIO_TOO_LARGE": {
        "mr": "ऑडिओ फाइल खूप मोठी आहे (जास्तीत जास्त 10 MB, 30 सेकंद).",
        "hi": "ऑडियो फ़ाइल बहुत बड़ी है (अधिकतम 10 MB, 30 सेकंड)।",
        "en": "Audio too large (max 10 MB, 30 seconds).",
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

_RETRYABLE: set[str] = {"UPSTREAM_UNAVAILABLE", "RATE_LIMITED", "STT_FAILED", "INTERNAL", "RUN_IN_PROGRESS"}


class AppError(Exception):
    """Raise this anywhere in the app; the FastAPI exception handler converts it."""

    def __init__(
        self,
        code: ErrorCode,
        details: dict | None = None,
        message: str | None = None,
        user_message: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.message = message or _USER_MSG[code]["en"]
        self.user_message = user_message or _USER_MSG[code]
        self.status_code = _STATUS[code]
        super().__init__(self.message)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                user_message=self.user_message,
                retryable=self.code in _RETRYABLE,
                details=self.details,
            )
        )

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail=self.to_response().model_dump(),
        )


_POSITIVE_MSG: dict[str, dict[str, str]] = {
    "land_acres": {
        "mr": "जमिनीचे क्षेत्र 0 पेक्षा जास्त असले पाहिजे.",
        "hi": "जमीन का क्षेत्रफल 0 से अधिक होना चाहिए।",
        "en": "Land area must be greater than 0 acres.",
    },
    "budget_rs": {
        "mr": "बजेट 0 पेक्षा जास्त असले पाहिजे.",
        "hi": "बजट 0 से अधिक होना चाहिए।",
        "en": "Budget must be greater than 0 rupees.",
    },
}


def ensure_positive(values: dict[str, object]) -> None:
    """Raise the standard 422 VALIDATION_ERROR if land_acres / budget_rs is not > 0."""
    bad: list[str] = []
    for field in ("land_acres", "budget_rs"):
        if field not in values:
            continue
        try:
            ok = float(values[field]) > 0  # type: ignore[arg-type]
        except (TypeError, ValueError):
            ok = False
        if not ok:
            bad.append(field)
    if not bad:
        return
    user_message = {
        lang: " ".join(_POSITIVE_MSG[f][lang] for f in bad) for lang in ("mr", "hi", "en")
    }
    raise AppError(
        "VALIDATION_ERROR",
        {"fields": bad},
        message=user_message["en"],
        user_message=user_message,
    )
