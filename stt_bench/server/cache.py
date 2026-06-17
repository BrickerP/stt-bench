"""Transcription result cache."""

from __future__ import annotations

import hashlib
import json

from stt_bench.models.config import ProviderConfig
from stt_bench.models.transcription import TranscriptionResult
from stt_bench.server.results.store import ResultsStore


def audio_hash(audio: bytes) -> str:
    return hashlib.sha256(audio).hexdigest()


def config_hash(config: ProviderConfig) -> str:
    canonical = json.dumps(config.config_hash_input(), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def cache_key(provider: str, audio: bytes, config: ProviderConfig) -> str:
    return f"{provider}:{audio_hash(audio)}:{config_hash(config)}"


class TranscriptionCache:
    def __init__(self, store: ResultsStore):
        self.store = store

    async def get(
        self, provider: str, audio: bytes, config: ProviderConfig
    ) -> TranscriptionResult | None:
        key = cache_key(provider, audio, config)
        result = await self.store.get_cache(key)
        if result:
            result.cache_hit = True
        return result

    async def set(
        self, provider: str, audio: bytes, config: ProviderConfig, result: TranscriptionResult
    ) -> None:
        key = cache_key(provider, audio, config)
        await self.store.set_cache(
            key, provider, audio_hash(audio), config_hash(config), result
        )
