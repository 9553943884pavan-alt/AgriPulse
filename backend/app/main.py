"""FastAPI application entry point.

Middleware: CORS, request-id injection, per-request timing, body-size limits.
Routers are registered here; each lives in app/api/.
"""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings

# ── Router imports (added as each phase is built) ────────────────────────────
from app.api import health  # E13 — always present

# ── Lifespan: warm up data loaders and ML models at startup ──────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1 / Phase 3 will register warm-up calls here.
    # For now we just signal readiness.
    app.state.ready = True
    yield
    app.state.ready = False


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="AgriPulse Backend",
    description=(
        "Crop planning API for smallholder farmers in Maharashtra. "
        "Every number shown to the farmer carries a source, date and status."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request-size limit (JSON ≤ 64 KB; audio handled per-endpoint) ─────────────

MAX_JSON_BYTES = 64 * 1024  # 64 KB

@app.middleware("http")
async def enforce_size_limit(request: Request, call_next):
    content_type = request.headers.get("content-type", "")
    if "multipart" not in content_type:  # skip audio uploads
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_JSON_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request body too large (max 64 KB for JSON).",
                        "user_message": {
                            "mr": "विनंती खूप मोठी आहे.",
                            "hi": "अनुरोध बहुत बड़ा है।",
                            "en": "Request body too large.",
                        },
                        "retryable": False,
                        "details": {},
                    }
                },
            )
    return await call_next(request)


# ── Request-id and Server-Timing middleware ───────────────────────────────────

@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-Id"] = request_id
    response.headers["Server-Timing"] = f"total;dur={elapsed_ms:.1f}"
    return response


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health.router, prefix="/api", tags=["health"])

# The remaining routers are registered as each phase completes:
# from app.api import agent, plan, threads, speech, prefetch, locations, sources
# app.include_router(agent.router, prefix="/api", tags=["agent"])
# … etc.
