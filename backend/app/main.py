"""FastAPI application entry point.

Middleware: CORS, request-id injection, per-request timing, body-size limits.
All routers registered here.
"""

import os
# Prevent OpenBLAS/MKL thread pool allocation failure on Windows / thread pools
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.errors import AppError

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api import agent, health, locations, plan, sources, speech, threads

# ── Lifespan: warm up data loaders and ML models at startup ──────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.data.loaders import load_all
    count = load_all()
    app.state.data_files_loaded = count

    # Pre-warm ML models (Model A and Hierarchical Median Baseline)
    try:
        from app.ml.yield_model import load_trained_model
        from app.ml.yield_baseline import get_yield_baseline
        m = load_trained_model()
        get_yield_baseline()
        app.state.models_loaded = m is not None
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to pre-warm ML models: %s", exc)
        app.state.models_loaded = False

    # Compile and attach the LangGraph agent graph
    try:
        from app.agent.graph import get_compiled_graph
        app.state.agent_graph = await get_compiled_graph()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "LangGraph agent failed to initialise (langgraph not installed?): %s", exc
        )
        app.state.agent_graph = None

    # Run one source-health probe in the background so /api/sources can report
    # live vs cached from evidence instead of assuming.
    probe_task = None
    try:
        import asyncio
        from app.api.sources import sources_health
        probe_task = asyncio.create_task(sources_health())
    except Exception:
        probe_task = None

    app.state.ready = True
    yield
    if probe_task is not None and not probe_task.done():
        probe_task.cancel()
    from app.core.cache import close_db
    from app.core.http_client import close_client
    await close_client()
    await close_db()
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
MAX_JSON_BYTES = 64 * 1024

@app.middleware("http")
async def enforce_size_limit(request: Request, call_next):
    content_type = request.headers.get("content-type", "")
    if "multipart" not in content_type:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_JSON_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": {"code": "VALIDATION_ERROR",
                                   "message": "Request body too large (max 64 KB).",
                                   "user_message": {"mr": "विनंती खूप मोठी आहे.", "hi": "अनुरोध बहुत बड़ा है।", "en": "Request too large."},
                                   "retryable": False, "details": {}}},
            )
    return await call_next(request)


# ── Request-id + Server-Timing ────────────────────────────────────────────────
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


# ── AppError exception handler ────────────────────────────────────────────────
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_response().model_dump())


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("app.unhandled").exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )
    # Log the exception above, but never reflect implementation/provider details
    # to clients.
    err = AppError("INTERNAL", {"path": request.url.path}, message="Internal server error")
    return JSONResponse(status_code=500, content=err.to_response().model_dump())


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
    err = AppError("VALIDATION_ERROR", {"fields": fields})
    return JSONResponse(status_code=422, content=err.to_response().model_dump())


# ── Router registration ────────────────────────────────────────────────────────
app.include_router(health.router,    prefix="/api", tags=["health"])
app.include_router(plan.router,      prefix="/api", tags=["plan"])
app.include_router(agent.router,     prefix="/api", tags=["agent"])
app.include_router(threads.router,   prefix="/api", tags=["threads"])
app.include_router(speech.router,    prefix="/api", tags=["speech"])
app.include_router(locations.router, prefix="/api", tags=["locations"])
app.include_router(sources.router,   prefix="/api", tags=["sources"])
