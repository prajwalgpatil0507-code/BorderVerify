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
# Runtime data directory. Defaults to a project-relative folder for local dev.
# In production set DATA_DIR to a mounted/persistent volume so user uploads and
# the SQLite database survive container restarts. SAMPLE_DIR (committed static
# demo assets) stays separate from the (potentially persistent) DATA_DIR so the
# built-in demo/synthetic cases always work even when DATA_DIR is a fresh volume.
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))  # project/data (shared)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads")))
SAMPLE_DIR = Path(os.getenv("SAMPLE_DIR", str(PROJECT_ROOT / "data" / "samples")))
DB_PATH = DATA_DIR / "border_verify.db"

# Ensure runtime directories exist
for _d in (UPLOAD_DIR, SAMPLE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _parse_csv(value: str) -> list[str]:
    """Parse a comma-separated environment value into a list of trimmed strings."""
    return [v.strip() for v in value.split(",") if v.strip()]


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
    # Comma-separated list of allowed CORS origins. In production set this to the
    # deployed frontend origin(s), e.g. "https://my-app.onrender.com". "*" allows
    # any origin (convenient for local dev; tighten it for production). The
    # frontend and backend are served from the same origin, so CORS is mainly
    # relevant only if the SPA is hosted separately from the API.
    CORS_ORIGINS: list = _parse_csv(os.getenv("CORS_ORIGINS", "*"))
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
        "passport_not_found": 40,        # document number absent from the reference DB
        "passport_field_mismatch": 45,   # found in DB but extracted identity fields conflict
        "document_anomaly": 20,          # inconsistent / suspicious document in the DB
        "image_quality_low": 12,         # image too blurry / dark / low-res to read reliably
        "liveness_not_live": 60,         # strong screen/print replay cue on a live capture
    }
    RISK_THRESHOLD_MEDIUM: int = int(os.getenv("RISK_THRESHOLD_MEDIUM", "30"))
    RISK_THRESHOLD_HIGH: int = int(os.getenv("RISK_THRESHOLD_HIGH", "61"))

    # --- Expiry ---
    EXPIRING_SOON_DAYS: int = int(os.getenv("EXPIRING_SOON_DAYS", "180"))

    # --- Face ---
    FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "0.62"))
    FACE_REVIEW_THRESHOLD: float = float(os.getenv("FACE_REVIEW_THRESHOLD", "0.78"))
    # Pre-trained ArcFace/InsightFace recognition model (512-d embeddings). When
    # present the deep embedding replaces the heuristic face matcher in
    # face.py. It is downloaded locally by _download_arcface.py and is NOT
    # committed (see .gitignore).
    FACE_EMBEDDING_MODEL: str = os.getenv(
        "FACE_EMBEDDING_MODEL", str(BASE_DIR / "arcface_w600k_r50.onnx"))

    # --- Gemini (optional AI-assisted document analysis) ---
    # The API key is read ONLY from the environment (populated from .env when
    # python-dotenv is available). It is never hardcoded and never sent to the
    # frontend. When absent, the AI layer is disabled and the existing pipeline
    # is used unchanged.
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    # Strict advisory timeout. Gemini is optional: if it is slow, returns 429/503
    # or exceeds this, verification continues immediately with the normal result.
    GEMINI_TIMEOUT_S: float = float(os.getenv("GEMINI_TIMEOUT_S", "6"))

    # --- Image processing bounds (speed vs accuracy for large uploads) ---
    # RapidOCR and the tamper heuristics re-scale images internally, so feeding
    # very large images mostly adds preprocessing cost (denoise / ELA) without
    # improving accuracy. These caps bound the working resolution before the
    # expensive steps so large uploads do not stall the pipeline.
    OCR_MAX_DIM: int = int(os.getenv("OCR_MAX_DIM", "1800"))
    OCR_UPSCALE_DIM: int = int(os.getenv("OCR_UPSCALE_DIM", "900"))
    TAMPER_MAX_DIM: int = int(os.getenv("TAMPER_MAX_DIM", "1200"))

    # --- Verification request safety ---
    # The CPU/IO-heavy verification pipeline runs in a Starlette worker thread
    # (off the asyncio event loop) so other endpoints stay responsive. This caps
    # how long a single verification request may take; if exceeded, the request
    # returns an error instead of leaving the client (and the pipeline) stuck.
    VERIFY_TIMEOUT_S: float = float(os.getenv("VERIFY_TIMEOUT_S", "30"))

    # --- Offline ---
    OFFLINE_MODE: bool = os.getenv("OFFLINE_MODE", "true").lower() in ("1", "true", "yes")

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
