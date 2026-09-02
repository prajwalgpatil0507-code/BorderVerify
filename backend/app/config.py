"""Application configuration.

Reads environment variables with safe defaults so the prototype runs out of the
box locally (no .env required), while still supporting production-style overrides
through environment variables / a `.env` file.
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # dotenv is optional
    pass


BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_ROOT = BASE_DIR.parent                              # project root
DATA_DIR = PROJECT_ROOT / "data"                            # project/data (shared)
UPLOAD_DIR = DATA_DIR / "uploads"
SAMPLE_DIR = DATA_DIR / "samples"
DB_PATH = DATA_DIR / "border_verify.db"

# Ensure runtime directories exist
for _d in (UPLOAD_DIR, SAMPLE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Settings:
    """Central settings object. Values can be overridden via env vars."""

    # --- Runtime directories (project-relative, created at import time) ---
    # These are exposed as instance attributes so callers can use
    # settings.UPLOAD_DIR, settings.SAMPLE_DIR, settings.DATA_DIR, settings.DB_PATH.
    BASE_DIR: Path = BASE_DIR
    PROJECT_ROOT: Path = PROJECT_ROOT
    DATA_DIR: Path = DATA_DIR
    UPLOAD_DIR: Path = UPLOAD_DIR
    SAMPLE_DIR: Path = SAMPLE_DIR
    DB_PATH: Path = DB_PATH

    # --- App ---
    APP_NAME: str = os.getenv("APP_NAME", "Zynovix BorderVerity")
    API_PREFIX: str = os.getenv("API_PREFIX", "/api")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "sih-zynovix-demo-secret-change-me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

    # --- MongoDB (live verification reference data) ---
    # The SIH synthetic demo dataset lives in MongoDB, NOT in a government DB.
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "borderverify")
    MONGODB_CONNECT_TIMEOUT_MS: int = int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "5000"))

    # Data-source transparency labels (used throughout the app / UI)
    DATA_SOURCE_LABEL: str = "SIH SYNTHETIC DEMO DATABASE"
    DATA_SOURCE_ENVIRONMENT: str = "DEMO / MOCK"
    GOVERNMENT_INTEGRATION: str = "NOT CONNECTED"
    FUTURE_INTEGRATION: str = "AUTHORIZED GOVERNMENT API"

    # --- Uploads / security ---
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "15"))
    ALLOWED_IMAGE_TYPES: tuple = (
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
        "image/tiff",
    )

    # --- Auth / demo officer (configurable via env, not hardcoded in frontend) ---
    DEMO_USERNAME: str = os.getenv("DEMO_USERNAME", "officer")
    DEMO_PASSWORD: str = os.getenv("DEMO_PASSWORD", "SIH@2026Demo")
    DEMO_NAME: str = os.getenv("DEMO_NAME", "Demo Officer")

    # --- OCR ---
    OCR_CONFIDENCE_THRESHOLD: float = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.5"))

    # --- Risk engine (tunable weights) ---
    # Weights are additive; score is clamped to 0-100.
    RISK_WEIGHTS: dict = {
        "invalid_mrz": 25,
        "ocr_mrz_mismatch": 40,
        "expired_passport": 30,
        "expiring_passport": 10,
        "expired_visa": 30,
        "face_mismatch": 65,
        "face_low_quality": 8,
        "watchlist_match": 65,
        "tamper_high": 70,
        "tamper_medium": 25,
        "duplicate_identity": 40,
        "blacklist": 70,
        "document_type_suspect": 15,
        "passport_not_found": 40,   # document number absent from the reference DB
        "document_anomaly": 20,     # inconsistent / suspicious document in the DB
    }
    RISK_THRESHOLD_MEDIUM: int = int(os.getenv("RISK_THRESHOLD_MEDIUM", "30"))
    RISK_THRESHOLD_HIGH: int = int(os.getenv("RISK_THRESHOLD_HIGH", "61"))

    # --- Expiry ---
    EXPIRING_SOON_DAYS: int = int(os.getenv("EXPIRING_SOON_DAYS", "180"))

    # --- Face ---
    FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "0.62"))
    FACE_REVIEW_THRESHOLD: float = float(os.getenv("FACE_REVIEW_THRESHOLD", "0.78"))

    # --- Offline ---
    OFFLINE_MODE: bool = os.getenv("OFFLINE_MODE", "true").lower() in ("1", "true", "yes")

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
