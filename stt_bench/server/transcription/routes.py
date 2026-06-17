"""Transcription REST routes."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from stt_bench.models.config import ProviderConfig
from stt_bench.server.deps import get_app_settings
from stt_bench.server.errors import APIError
from stt_bench.server.transcription.service import TranscriptionService
from stt_bench.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["transcription"])


class TranscribeRequest(BaseModel):
    audio_path: str | None = None
    provider: str
    config: ProviderConfig
    force: bool = False


def _get_transcription_service(request: Request) -> TranscriptionService:
    return request.app.state.transcription_service


@router.post("/transcribe")
async def transcribe(
    request: Request,
    body: TranscribeRequest | None = None,
    settings: Settings = Depends(get_app_settings),
    file: UploadFile | None = File(None),
    config: str | None = Form(None),
    provider: str | None = Form(None),
    force: bool = Form(False),
):
    svc = _get_transcription_service(request)

    if file is not None:
        audio = await file.read()
        cfg = ProviderConfig.model_validate_json(config) if config else ProviderConfig(
            provider=provider or "mock", model="mock-v1"
        )
        prov = provider or cfg.provider
        result = await svc.transcribe(audio, prov, cfg, force=force)
        return result

    if body is None:
        raise APIError("INVALID_REQUEST", "Request body required", 422)

    if body.audio_path:
        path = settings.resolve_path(body.audio_path)
        if not path.is_absolute():
            path = (settings.data_dir / body.audio_path).resolve()
        result = await svc.transcribe_path(path, body.provider, body.config, force=body.force)
        return result

    raise APIError("AUDIO_NOT_FOUND", "audio_path or file required", 404)


@router.post("/transcribe/stream")
async def transcribe_stream(
    request: Request,
    body: TranscribeRequest,
    settings: Settings = Depends(get_app_settings),
):
    svc = _get_transcription_service(request)

    if body.config.transport_mode != "streaming":
        raise APIError("TRANSPORT_NOT_SUPPORTED", "transport_mode must be streaming", 422)

    if not body.audio_path:
        raise APIError("AUDIO_NOT_FOUND", "audio_path required", 404)

    path = settings.resolve_path(body.audio_path)
    if not path.exists():
        path = (settings.data_dir / body.audio_path).resolve()
    audio = path.read_bytes()

    async def event_generator():
        async for event in svc.transcribe_stream_events(audio, body.provider, body.config):
            if event["type"] == "partial":
                p = event["data"]
                yield {
                    "event": "partial",
                    "data": json.dumps({
                        "text": p.text,
                        "is_final": p.is_final,
                        "timestamp_ms": p.timestamp_ms,
                    }),
                }
            else:
                r = event["data"]
                yield {
                    "event": "done",
                    "data": r.model_dump_json(),
                }

    return EventSourceResponse(event_generator())


@router.get("/transcribe/{result_id}")
async def get_transcription(result_id: str, request: Request):
    store = request.app.state.store
    result = await store.get_transcription_by_id(result_id)
    if not result:
        raise APIError("TRANSCRIBE_FAILED", f"Result not found: {result_id}", 404)
    return result
