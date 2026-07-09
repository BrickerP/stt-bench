"""AssemblyAI batch STT provider adapter.

CI and unit tests must not call the live API. Use mock provider or contract tests.
Manual smoke: set ASSEMBLYAI_API_KEY and run a single-file transcribe locally.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

import httpx

from stt_bench.metrics.cost import estimate_provider_cost
from stt_bench.models.config import ProviderCapabilities, ProviderConfig
from stt_bench.models.transcription import Timings, TranscriptionResult
from stt_bench.providers.base import (
    ProviderError,
    STTProvider,
    StreamPartial,
    TransportNotSupported,
    estimate_audio_duration_s,
    register_provider,
)

_BASE = "https://api.assemblyai.com/v2"


@register_provider
class AssemblyAIProvider(STTProvider):
    name = "assemblyai"
    display_name = "AssemblyAI"
    capabilities = ProviderCapabilities(
        supports_batch=True,
        supports_streaming=False,
        supports_confidence=True,
        supports_word_timestamps=True,
    )

    def _api_key(self) -> str:
        key = getattr(self.settings, "assemblyai_api_key", None)
        if not key:
            raise ProviderError(
                "PROVIDER_AUTH_FAILED",
                "ASSEMBLYAI_API_KEY not configured",
                401,
            )
        return key

    def _headers(self) -> dict[str, str]:
        return {"authorization": self._api_key()}

    async def validate_config(self, config: ProviderConfig) -> None:
        self._api_key()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{_BASE}/transcript", headers=self._headers(), params={"limit": 1})
            if resp.status_code in (401, 403):
                raise ProviderError("PROVIDER_AUTH_FAILED", "AssemblyAI auth failed", 401)
            if resp.status_code >= 500:
                raise ProviderError("PROVIDER_UPSTREAM_ERROR", f"AssemblyAI error: {resp.status_code}", 502)

    async def transcribe_batch(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> TranscriptionResult:
        duration_s = estimate_audio_duration_s(audio)
        start = time.perf_counter()
        headers = self._headers()

        async with httpx.AsyncClient(timeout=120.0) as client:
            upload = await client.post(f"{_BASE}/upload", headers=headers, content=audio)
            if upload.status_code >= 400:
                raise ProviderError(
                    "PROVIDER_UPSTREAM_ERROR",
                    f"AssemblyAI upload failed: {upload.status_code} {upload.text[:200]}",
                    502,
                )
            upload_url = upload.json().get("upload_url")
            if not upload_url:
                raise ProviderError("PROVIDER_UPSTREAM_ERROR", "AssemblyAI upload missing upload_url", 502)

            payload: dict = {
                "audio_url": upload_url,
                "language_code": config.language or "en",
            }
            if config.model and config.model not in {"default", "best"}:
                payload["speech_model"] = config.model
            create = await client.post(
                f"{_BASE}/transcript",
                headers={**headers, "content-type": "application/json"},
                json=payload,
            )
            if create.status_code >= 400:
                raise ProviderError(
                    "PROVIDER_UPSTREAM_ERROR",
                    f"AssemblyAI create failed: {create.status_code} {create.text[:200]}",
                    502,
                )
            transcript_id = create.json()["id"]

            text = ""
            status = "queued"
            for _ in range(120):
                poll = await client.get(f"{_BASE}/transcript/{transcript_id}", headers=headers)
                if poll.status_code >= 400:
                    raise ProviderError(
                        "PROVIDER_UPSTREAM_ERROR",
                        f"AssemblyAI poll failed: {poll.status_code}",
                        502,
                    )
                body = poll.json()
                status = body.get("status", "error")
                if status == "completed":
                    text = (body.get("text") or "").strip()
                    break
                if status == "error":
                    raise ProviderError(
                        "PROVIDER_UPSTREAM_ERROR",
                        f"AssemblyAI transcription error: {body.get('error')}",
                        502,
                    )
                await asyncio.sleep(0.5)
            else:
                raise ProviderError("PROVIDER_UPSTREAM_ERROR", "AssemblyAI transcription timed out", 502)

        total_ms = (time.perf_counter() - start) * 1000
        return TranscriptionResult(
            id=f"tr_{uuid.uuid4().hex[:12]}",
            provider="assemblyai",
            transport_mode="batch",
            text=text,
            audio_duration_s=duration_s,
            timings=Timings(
                ttft_ms=None,
                total_ms=total_ms,
                rtf=total_ms / (duration_s * 1000) if duration_s > 0 else 0.0,
            ),
            cost_usd=self.estimate_cost_usd(duration_s, config),
            cache_hit=False,
            raw_provider_response={"id": transcript_id, "status": status},
        )

    async def transcribe_stream(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> AsyncIterator[StreamPartial]:
        raise TransportNotSupported("assemblyai", "streaming")
        yield  # pragma: no cover

    def estimate_cost_usd(self, audio_duration_s: float, config: ProviderConfig) -> float:
        return estimate_provider_cost("assemblyai", config.model, audio_duration_s, self.settings)

    def default_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider="assemblyai",
            model=getattr(self.settings, "assemblyai_model", "best"),
            language="en",
            transport_mode="batch",
        )
