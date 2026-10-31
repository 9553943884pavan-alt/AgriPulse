"""E13  GET /api/health

Returns app status, whether ML models are loaded, and how many data files
are available. Used as the deployment warm-up ping.
"""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    """Deployment check and warm-up ping.

    Returns 200 as soon as the app is up.  models_loaded and data_files are
    updated in-place by the lifespan warm-up once the data layer exists.
    """
    return {
        "status": "ok",
        "models_loaded": getattr(request.app.state, "models_loaded", False),
        "data_files": getattr(request.app.state, "data_files_loaded", 0),
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
