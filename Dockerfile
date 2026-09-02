# Zynovix BorderVerity — monolithic image that serves BOTH the FastAPI backend
# and the frontend SPA, so the app runs as a single service (recommended for the
# deployment; the API + UI share a public URL and verify results render directly).
#
# NOTE: Python 3.11 is required because rapidocr_onnxruntime has no wheels for
# Python 3.13. Do NOT bump the base image to 3.12/3.13 without confirming a wheel.
FROM python:3.11-slim-bullseye

WORKDIR /app

# OS libraries required by OpenCV (cv2) + RapidOCR + onnxruntime, and curl for
# health checks. Kept minimal to keep the image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching).
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Application code + the static filesystem layout the app expects:
#   /app/backend/app  -> the FastAPI package
#   /app/frontend     -> the SPA (served at / and /static)
#   /app/data/samples -> committed demo/synthetic sample images (read-only assets)
COPY backend /app/backend
COPY frontend /app/frontend
COPY data/samples /app/data/samples

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend
# DATA_DIR defaults to /app/data inside the container. Mount a persistent volume
# there (see render.yaml / platform) so uploads and the SQLite DB survive restarts.
RUN mkdir -p /app/data/uploads /app/data/samples

EXPOSE 8000

# $PORT is provided by Render / Heroku / other container hosts.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
