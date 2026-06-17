"""Transcription orchestration service."""

from __future__ import annotations

import uuid
from pathlib import Path

from stt_bench.models.config import ProviderConfig
from stt_bench.models.transcription import TranscriptionResult
from stt_bench.providers.base import ProviderError, get_provider
from stt_bench.server.cache import TranscriptionCache
from stt_bench.settings import Settings


class TranscriptionService:
    def __init__(self, settings: Settings, cache: TranscriptionCache):
        self.settings = settings
        self.cache = cache

    async def transcribe(
        self,
        audio: bytes,
        provider_name: str,
        config: ProviderConfig,
        force: bool = False,
        reference_text: str | None = None,
    ) -> TranscriptionResult:
        if reference_text and config.provider == "mock":
            config = config.model_copy(deep=True)
            config.extra = {**config.extra, "reference_text": reference_text}

        if not force:
            cached = await self.cache.get(provider_name, audio, config)
            if cached:
                return cached

        provider = get_provider(provider_name, self.settings)
        result_id = f"tr_{uuid.uuid4().hex[:12]}"
        result = await provider.transcribe(audio, config, result_id=result_id)
        result.cache_hit = False

        await self.cache.set(provider_name, audio, config, result)
        return result

    async def transcribe_path(
        self,
        audio_path: Path,
        provider_name: str,
        config: ProviderConfig,
        force: bool = False,
        reference_text: str | None = None,
    ) -> TranscriptionResult:
        if not audio_path.exists():
            raise ProviderError("AUDIO_NOT_FOUND", f"Audio not found: {audio_path}", 404)
        audio = audio_path.read_bytes()
        if not audio:
            raise ProviderError("AUDIO_INVALID", "Empty audio file", 422)
        return await self.transcribe(audio, provider_name, config, force, reference_text)

    async def transcribe_stream_events(
        self,
        audio: bytes,
        provider_name: str,
        config: ProviderConfig,
        reference_text: str | None = None,
    ):
        """Async generator of StreamPartial dicts + final result."""
        if reference_text and config.provider == "mock":
            config = config.model_copy(deep=True)
            config.extra = {**config.extra, "reference_text": reference_text}

        provider = get_provider(provider_name, self.settings)
        parts = []
        async for partial in provider.transcribe_stream(audio, config):
            parts.append(partial)
            yield {"type": "partial", "data": partial}

        result_id = f"tr_{uuid.uuid4().hex[:12]}"
        result = provider._partials_to_result(parts, config, result_id, audio)
        await self.cache.set(provider_name, audio, config, result)
        yield {"type": "done", "data": result}
