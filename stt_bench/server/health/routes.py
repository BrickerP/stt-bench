"""Health and config routes."""

from fastapi import APIRouter, Depends

from stt_bench.dataset.loader import validate_dataset
from stt_bench.server.deps import get_app_settings
from stt_bench.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(settings: Settings = Depends(get_app_settings)):
    ds = validate_dataset(settings)
    checks = {
        "database": "ok",
        "openai_key": "configured" if settings.openai_api_key else "missing",
        "deepgram_key": "configured" if settings.deepgram_api_key else "missing",
        "dataset": "ok" if ds["valid"] else "invalid",
    }
    status = "ready" if ds["valid"] else "degraded"
    return {"status": status, "checks": checks}


@router.get("/config")
async def config(settings: Settings = Depends(get_app_settings)):
    return {
        "host": settings.stt_bench_host,
        "port": settings.stt_bench_port,
        "data_dir": str(settings.data_dir),
        "db_path": str(settings.db_path),
        "whisper_model": settings.whisper_model,
        "deepgram_model": settings.deepgram_model,
        "openai_key": "***" if settings.openai_api_key else None,
        "deepgram_key": "***" if settings.deepgram_api_key else None,
    }
