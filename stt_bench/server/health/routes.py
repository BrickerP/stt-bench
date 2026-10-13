"""Health and config routes."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Depends

from stt_bench.dataset.loader import validate_dataset
from stt_bench.server.deps import get_app_settings
from stt_bench.settings import Settings

router = APIRouter(tags=["health"])


def _package_version() -> str:
    try:
        return version("stt-eval-bench")
    except PackageNotFoundError:
        return "0.1.0"


@router.get("/healthz")
@router.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@router.get("/readyz")
@router.get("/api/v1/health/ready")
async def ready(settings: Settings = Depends(get_app_settings)):
    ds = validate_dataset(settings)
    checks = {
        "database": "ok",
        "openai_key": "configured" if settings.openai_api_key else "missing",
        "deepgram_key": "configured" if settings.deepgram_api_key else "missing",
        "assemblyai_key": "configured" if settings.assemblyai_api_key else "missing",
        "google_credentials": "configured" if settings.google_application_credentials else "missing",
        "azure_speech_key": "configured" if settings.azure_speech_key else "missing",
        "azure_speech_region": "configured" if settings.azure_speech_region else "missing",
        "dataset": "ok" if ds["valid"] else "invalid",
    }
    status = "ready" if ds["valid"] else "degraded"
    return {"status": status, "checks": checks}


@router.get("/version")
@router.get("/api/v1/version")
async def version_route():
    return {"name": "stt-eval-bench", "version": _package_version(), "cli": "stt-bench"}


@router.get("/api/v1/config")
async def config(settings: Settings = Depends(get_app_settings)):
    return {
        "host": settings.stt_bench_host,
        "port": settings.stt_bench_port,
        "data_dir": str(settings.data_dir),
        "db_path": str(settings.db_path),
        "whisper_model": settings.whisper_model,
        "deepgram_model": settings.deepgram_model,
        "assemblyai_model": settings.assemblyai_model,
        "google_speech_model": settings.google_speech_model,
        "azure_speech_model": settings.azure_speech_model,
        "openai_key": "***" if settings.openai_api_key else None,
        "deepgram_key": "***" if settings.deepgram_api_key else None,
        "assemblyai_key": "***" if settings.assemblyai_api_key else None,
        "google_credentials": "***" if settings.google_application_credentials else None,
        "azure_speech_key": "***" if settings.azure_speech_key else None,
        "azure_speech_region": settings.azure_speech_region,
    }
