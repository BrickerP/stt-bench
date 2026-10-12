"""Mock STT provider for CI and offline testing."""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections.abc import AsyncIterator

from stt_bench.models.config import ProviderCapabilities, ProviderConfig
from stt_bench.models.transcription import Timings, TranscriptionResult
from stt_bench.providers.base import (
    StreamPartial,
    STTProvider,
    estimate_audio_duration_s,
    register_provider,
)


@register_provider
class MockProvider(STTProvider):
    name = "mock"
    display_name = "Mock Provider"
    capabilities = ProviderCapabilities(
        supports_batch=True,
        supports_streaming=True,
        supports_confidence=True,
        supports_word_timestamps=False,
    )

    async def validate_config(self, config: ProviderConfig) -> None:
        return

    def _get_reference_text(self, config: ProviderConfig) -> str:
        return config.extra.get(
            "reference_text",
            "he hoped there would be stew for dinner turnips and carrots and bruised potatoes",
        )

    def _maybe_mutate(self, text: str, config: ProviderConfig) -> str:
        error_rate = float(config.extra.get("error_rate", 0.0))
        if error_rate <= 0:
            return text.lower()
        words = text.lower().split()
        if not words:
            return text.lower()
        rng = random.Random(config.extra.get("seed", 42))
        if rng.random() < error_rate and len(words) > 1:
            idx = rng.randint(0, len(words) - 1)
            words[idx] = "xxx"
        return " ".join(words)

    async def transcribe_batch(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> TranscriptionResult:
        latency_ms = float(config.extra.get("latency_ms", 100))
        await asyncio.sleep(latency_ms / 1000.0)

        duration_s = estimate_audio_duration_s(audio)
        text = self._maybe_mutate(self._get_reference_text(config), config)
        total_ms = latency_ms

        return TranscriptionResult(
            id=f"tr_{uuid.uuid4().hex[:12]}",
            provider="mock",
            transport_mode="batch",
            text=text,
            audio_duration_s=duration_s,
            timings=Timings(
                ttft_ms=None,
                total_ms=total_ms,
                rtf=total_ms / (duration_s * 1000) if duration_s > 0 else 0.0,
            ),
            cost_usd=0.0,
            cache_hit=False,
        )

    async def transcribe_stream(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> AsyncIterator[StreamPartial]:
        latency_ms = float(config.extra.get("latency_ms", 50))
        chunk_delay = latency_ms / 5.0
        text = self._maybe_mutate(self._get_reference_text(config), config)
        words = text.split()
        start = time.perf_counter()

        accumulated = ""
        for i, word in enumerate(words):
            await asyncio.sleep(chunk_delay / 1000.0)
            accumulated = f"{accumulated} {word}".strip()
            elapsed_ms = (time.perf_counter() - start) * 1000
            is_final = i == len(words) - 1
            yield StreamPartial(
                text=accumulated,
                is_final=is_final,
                timestamp_ms=elapsed_ms,
                confidence=0.9 + random.random() * 0.1,
            )

        # Ensure we processed audio duration context
        _ = estimate_audio_duration_s(audio)

    def estimate_cost_usd(self, audio_duration_s: float, config: ProviderConfig) -> float:
        return 0.0

    def default_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider="mock",
            model="mock-v1",
            language="en",
            transport_mode="batch",
            extra={"latency_ms": 50, "error_rate": 0.0},
        )
