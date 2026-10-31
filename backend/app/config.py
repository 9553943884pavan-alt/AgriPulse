"""Application settings loaded from .env via pydantic-settings.

All environment variable names are defined here and in .env.example.
No key is ever set as a code default; missing required keys raise a clear error
at startup rather than silently using a wrong value.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Pilot state ──────────────────────────────────────────────────────────
    STATE: str = "Maharashtra"

    # ── External API keys ────────────────────────────────────────────────────
    DATA_GOV_IN_API_KEY: str = ""        # Agmarknet mandi prices, CWC reservoirs
    SARVAM_API_KEY: str = ""             # The only model provider

    # ── Sarvam model IDs (from B10 test report, kept in .env not in code) ───
    SARVAM_CHAT_MODEL: str = ""
    SARVAM_STT_MODEL: str = ""
    SARVAM_TTS_MODEL: str = ""
    SARVAM_FALLBACK_MODELS: str = ""     # comma-separated chat model ids

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"  # safe local default

    # ── SQLite cache ─────────────────────────────────────────────────────────
    CACHE_DB_PATH: str = "cache.db"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sarvam_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.SARVAM_FALLBACK_MODELS.split(",") if m.strip()]


settings = Settings()
