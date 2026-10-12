"""OpenAI Whisper batch transcription provider."""

from __future__ import annotations

import io
import time
import uuid
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from stt_bench.metrics.cost import estimate_provider_cost
from stt_bench.models.config import ProviderCapabilities, ProviderConfig
from stt_bench.models.transcription import Timings, TranscriptionResult
from stt_bench.providers.base import (
    StreamPartial,
    STTProvider,
    TransportNotSupported,
    estimate_audio_duration_s,
    register_provider,
)


@register_provider
class WhisperProvider(STTProvider):
    name = "whisper"
    display_name = "OpenAI Whisper"
    capabilities = ProviderCapabilities(
        supports_batch=True,
        supports_streaming=False,
        supports_confidence=False,
        supports_word_timestamps=True,
    )

    def _client(self) -> AsyncOpenAI:
        if not self.settings.openai_api_key:
            from stt_bench.providers.base import ProviderError

            raise ProviderError("PROVIDER_AUTH_FAILED", "OPENAI_API_KEY not configured", 401)
        return AsyncOpenAI(api_key=self.settings.openai_api_key)

    async def validate_config(self, config: ProviderConfig) -> None:
        client = self._client()
        # Minimal validation: list models or a tiny check
        try:
            await client.models.list()
        except Exception as e:
            from stt_bench.providers.base import ProviderError

            raise ProviderError("PROVIDER_AUTH_FAILED", f"OpenAI auth failed: {e}", 401) from e

    async def transcribe_batch(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> TranscriptionResult:
        client = self._client()
        duration_s = estimate_audio_duration_s(audio)
        start = time.perf_counter()

        response_format = config.extra.get("response_format", "json")
        temperature = float(config.extra.get("temperature", 0))

        file_obj = io.BytesIO(audio)
        file_obj.name = "audio.flac"

        response = await client.audio.transcriptions.create(
            model=config.model,
            file=file_obj,
            language=config.language,
            response_format=response_format,
            temperature=temperature,
        )

        total_ms = (time.perf_counter() - start) * 1000
        text = response if isinstance(response, str) else getattr(response, "text", str(response))

        return TranscriptionResult(
            id=f"tr_{uuid.uuid4().hex[:12]}",
            provider="whisper",
            transport_mode="batch",
            text=text.strip(),
            audio_duration_s=duration_s,
            timings=Timings(
                ttft_ms=None,
                total_ms=total_ms,
                rtf=total_ms / (duration_s * 1000) if duration_s > 0 else 0.0,
            ),
            cost_usd=self.estimate_cost_usd(duration_s, config),
            cache_hit=False,
            raw_provider_response={"text": text} if isinstance(text, str) else None,
        )

    async def transcribe_stream(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> AsyncIterator[StreamPartial]:
        raise TransportNotSupported("whisper", "streaming")
        yield  # pragma: no cover

    def estimate_cost_usd(self, audio_duration_s: float, config: ProviderConfig) -> float:
        return estimate_provider_cost("whisper", config.model, audio_duration_s, self.settings)

    def default_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider="whisper",
            model=self.settings.whisper_model,
            language="en",
            transport_mode="batch",
        )
