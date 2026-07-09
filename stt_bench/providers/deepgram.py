"""Deepgram streaming transcription provider."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

import websockets

from stt_bench.metrics.cost import estimate_provider_cost
from stt_bench.models.config import ProviderCapabilities, ProviderConfig
from stt_bench.providers.base import (
    STTProvider,
    StreamPartial,
    TransportNotSupported,
    ProviderError,
    estimate_audio_duration_s,
    register_provider,
)


@register_provider
class DeepgramProvider(STTProvider):
    name = "deepgram"
    display_name = "Deepgram"
    capabilities = ProviderCapabilities(
        supports_batch=False,
        supports_streaming=True,
        supports_confidence=True,
        supports_word_timestamps=True,
    )

    def _require_key(self) -> str:
        if not self.settings.deepgram_api_key:
            from stt_bench.providers.base import ProviderError

            raise ProviderError("PROVIDER_AUTH_FAILED", "DEEPGRAM_API_KEY not configured", 401)
        return self.settings.deepgram_api_key

    async def validate_config(self, config: ProviderConfig) -> None:
        self._require_key()

    async def transcribe_batch(
        self,
        audio: bytes,
        config: ProviderConfig,
    ):

        raise TransportNotSupported("deepgram", "batch")

    async def transcribe_stream(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> AsyncIterator[StreamPartial]:
        api_key = self._require_key()
        _ = estimate_audio_duration_s(audio)

        punctuate = config.extra.get("punctuate", True)
        interim = config.extra.get("interim_results", True)
        endpointing = config.extra.get("endpointing_ms", 300)

        params = {
            "model": config.model,
            "language": config.language,
            "punctuate": str(punctuate).lower(),
            "interim_results": str(interim).lower(),
            "endpointing": str(endpointing),
        }
        # Send FLAC bytes directly
        if audio[:4] == b"fLaC":
            params["encoding"] = "flac"
        else:
            params["encoding"] = "linear16"
            params["sample_rate"] = "16000"
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"wss://api.deepgram.com/v1/listen?{query}"

        start = time.perf_counter()

        chunk_size = 4096
        chunks = [audio[i : i + chunk_size] for i in range(0, len(audio), chunk_size)]

        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                async for partial in self._stream_once(url, api_key, chunks, start):
                    yield partial
                return
            except (TimeoutError, OSError, websockets.exceptions.WebSocketException) as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5 * (2**attempt))
                    continue
                raise ProviderError(
                    "PROVIDER_TIMEOUT",
                    f"Deepgram WebSocket failed after {max_retries} attempts: {exc}",
                    504,
                ) from exc

        if last_error:
            raise ProviderError(
                "PROVIDER_TIMEOUT",
                f"Deepgram WebSocket failed: {last_error}",
                504,
            ) from last_error

    async def _stream_once(
        self,
        url: str,
        api_key: str,
        chunks: list[bytes],
        start: float,
    ) -> AsyncIterator[StreamPartial]:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {api_key}"},
            open_timeout=45,
            close_timeout=15,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            async def sender():
                for chunk in chunks:
                    await ws.send(chunk)
                    await asyncio.sleep(0.02)
                await ws.send(json.dumps({"type": "CloseStream"}))

            send_task = asyncio.create_task(sender())

            try:
                async for message in ws:
                    if isinstance(message, bytes):
                        continue
                    data = json.loads(message)
                    channel = data.get("channel", {})
                    alts = channel.get("alternatives", [])
                    if not alts:
                        continue

                    text = alts[0].get("transcript", "")
                    confidence = alts[0].get("confidence")
                    is_final = data.get("is_final", False) or data.get("speech_final", False)
                    elapsed_ms = (time.perf_counter() - start) * 1000

                    if text.strip() or is_final:
                        yield StreamPartial(
                            text=text,
                            is_final=is_final,
                            timestamp_ms=elapsed_ms,
                            confidence=confidence,
                        )

                    if data.get("type") == "Results" and is_final and not text.strip():
                        pass
            finally:
                await send_task

    def estimate_cost_usd(self, audio_duration_s: float, config: ProviderConfig) -> float:
        return estimate_provider_cost("deepgram", config.model, audio_duration_s, self.settings)

    def default_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider="deepgram",
            model=self.settings.deepgram_model,
            language="en",
            transport_mode="streaming",
            extra={"punctuate": True, "interim_results": True, "endpointing_ms": 300},
        )
