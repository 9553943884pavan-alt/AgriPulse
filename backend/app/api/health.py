"""E13  GET /api/health

Returns app status, whether ML models are loaded, and how many data files
are available. Used as the deployment warm-up ping.
"""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    """Deployment check and warm-up ping.

    Returns 200 as soon as the app is up. models_loaded and data_files are
    updated in-place by the lifespan warm-up.
    """
    models_loaded = getattr(request.app.state, "models_loaded", None)
    if not models_loaded:
        try:
            from app.ml.yield_model import load_trained_model
            from app.ml.yield_baseline import get_yield_baseline
            m = load_trained_model()
            get_yield_baseline()
            models_loaded = m is not None
            request.app.state.models_loaded = models_loaded
        except Exception:
            models_loaded = False

    return {
        "status": "ok",
        "models_loaded": bool(models_loaded),
        "data_files": getattr(request.app.state, "data_files_loaded", 18),
        "version": "0.1.0",
    }


@router.get("/schemas/sse-events")
async def sse_schemas() -> dict:
    """C.4 — exposes every SSE payload as an OpenAPI-visible response model.

    OpenAPI cannot describe a stream, so this stub endpoint declares all SSE
    event shapes so the TypeScript generator picks them up.  The frontend
    generates its types from these; it must not hand-write them.
    """
    from app.schemas import SSEEventExamples  # noqa: F401 — triggers OpenAPI registration
    return {"note": "See SSEEventExamples schema for all SSE event shapes."}
