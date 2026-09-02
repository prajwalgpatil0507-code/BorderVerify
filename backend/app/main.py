"""FastAPI application entrypoint for Zynovix BorderVerity."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import settings, DATA_DIR
from .core.deps import configure_logging
from .models.models import init_db
from .routers import auth, verify, dashboard, demo, database as database_router
from .db import mongo as mongo_db

configure_logging()

DATA_DIR.mkdir(exist_ok=True)


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version="1.0.0",
    description="AI-powered travel document verification and fraud detection "
                "prototype (Smart India Hackathon).",
)

# CORS origins come from settings (env-driven) so production can pin them to the
# deployed frontend origin instead of the permissive local-dev default.
_cors_origins = settings.CORS_ORIGINS or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = settings.API_PREFIX
app.include_router(auth.router, prefix=f"{API}/auth")
app.include_router(verify.router, prefix=API)
app.include_router(dashboard.router, prefix=API)
app.include_router(demo.router, prefix=API)
app.include_router(database_router.router, prefix=API)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    # Best-effort: create Mongo indexes if the demo database is reachable.
    try:
        if mongo_db.mongo_available():
            mongo_db.ensure_indexes()
    except Exception:  # noqa: BLE001
        pass
    # Eagerly load the OCR engine so the FIRST verification request does not pay
    # the (multi-second) RapidOCR model-load cost inside the user's request.
    # Best-effort: if the engine cannot initialise, verification falls back to
    # graceful degradation exactly as it does today.
    try:
        from .services import ocr as _ocr
        _ocr._get_engine()
    except Exception:  # noqa: BLE001
        pass


@app.get("/")
def index():
    """Serve the frontend SPA."""
    frontend = Path(__file__).resolve().parent.parent.parent / "frontend"
    index_file = frontend / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "BorderVerity API is running. Start the frontend to use the dashboard."}


@app.get(f"{API}/health")
def health():
    mongo_ok = mongo_db.mongo_available()
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "offline_mode": settings.OFFLINE_MODE,
        "mongo": {
            "available": mongo_ok,
            "database": mongo_db.database_name(),
            "version": None,
        },
        "data_source": settings.DATA_SOURCE_LABEL,
        "environment": settings.DATA_SOURCE_ENVIRONMENT,
        "government_integration": settings.GOVERNMENT_INTEGRATION,
    }


# Mount static assets (css/js/img) if present.
_static = Path(__file__).resolve().parent.parent.parent / "frontend"
if _static.exists() and (_static / "css").exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")

    # The SPA references assets with root-relative paths (e.g. "css/style.css")
    # so it also runs as a pure static site (e.g. GitHub Pages). Serve the
    # asset folders at those same paths for the local FastAPI app.
    for _sub in ("css", "js", "img"):
        _sub_path = _static / _sub
        if (_sub_path).exists():
            app.mount(f"/{_sub}", StaticFiles(directory=str(_sub_path)), name=_sub)

# Serve uploaded + sample media (uploads/, samples/) under /media.
if DATA_DIR.exists():
    app.mount("/media", StaticFiles(directory=str(DATA_DIR)), name="media")


if __name__ == "__main__":
    import uvicorn
    # Bind to 0.0.0.0 and honour the platform-supplied PORT so the same entry
    # point works for local dev (uvicorn app.main:app) and container hosts
    # (Render sets $PORT; Docker/heroku set $PORT too).
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() in ("1", "true", "yes"),
    )
