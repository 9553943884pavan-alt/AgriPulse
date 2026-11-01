# AgriPulse backend (FastAPI + ML models + optimizer + LangGraph agent).
# Build from the repo root:   docker build -t agripulse-backend .
# Run locally:                docker run --rm -p 7860:7860 --env-file .env agripulse-backend
# Works on Hugging Face Spaces (Docker SDK, port 7860) and any host that sets $PORT.
# Secrets (SARVAM_API_KEY, DATA_GOV_IN_API_KEY, ...) come from the host's environment,
# never from this image: .env is excluded by .dockerignore.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    CACHE_DB_PATH=/app/backend/data/cache.db

# OpenMP runtime for scikit-learn / LightGBM wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs containers as uid 1000
RUN useradd -m -u 1000 user

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# The backend resolves these paths from the repo root (/app):
#   data/processed/  -> backend/app/data/loaders.py
#   ml/models/       -> backend/app/ml/yield_model.py
COPY backend/app backend/app
COPY data/processed data/processed
COPY ml/models ml/models

# Only writable location the app needs: the SQLite cache + agent memory
RUN mkdir -p backend/data && chown -R user:user /app/backend/data

USER user
WORKDIR /app/backend
EXPOSE 7860

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]
