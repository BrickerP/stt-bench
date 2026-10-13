"""Provider base class and registry."""

from __future__ import annotations

import wave
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING

from stt_bench.metrics.revision import compute_partial_revision, group_interim_hypotheses
from stt_bench.models.config import ProviderCapabilities, ProviderConfig, TransportMode
from stt_bench.models.transcription import ConfidenceMetrics, Timings, TranscriptionResult

if TYPE_CHECKING:
    from stt_bench.settings import Settings


class ProviderError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class TransportNotSupported(ProviderError):
    def __init__(self, provider: str, mode: str):
        super().__init__(
            "TRANSPORT_NOT_SUPPORTED",
            f"Provider '{provider}' does not support transport mode '{mode}'",
            status_code=422,
        )


@dataclass
class StreamPartial:
    text: str
    is_final: bool
    timestamp_ms: float
    confidence: float | None = None


class STTProvider(ABC):
    name: str
    display_name: str
    capabilities: ProviderCapabilities

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    async def validate_config(self, config: ProviderConfig) -> None:
        """Raise ProviderError if config or credentials invalid."""

    @abstractmethod
    async def transcribe_batch(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> TranscriptionResult:
        """Full-file batch transcription."""

    @abstractmethod
    async def transcribe_stream(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> AsyncIterator[StreamPartial]:
        """Yield partial results; final partial has is_final=True."""
        yield StreamPartial(text="", is_final=True, timestamp_ms=0)  # pragma: no cover

    async def transcribe(
        self,
        audio: bytes,
        config: ProviderConfig,
        result_id: str | None = None,
    ) -> TranscriptionResult:
        """Dispatch by config.transport_mode."""
        import uuid

        rid = result_id or f"tr_{uuid.uuid4().hex[:12]}"
        mode = TransportMode(config.transport_mode)

        if mode == TransportMode.BATCH:
            if not self.capabilities.supports_batch:
                raise TransportNotSupported(self.name, "batch")
            result = await self.transcribe_batch(audio, config)
            result.id = rid
            return result

        if not self.capabilities.supports_streaming:
            raise TransportNotSupported(self.name, "streaming")

        parts: list[StreamPartial] = []
        async for p in self.transcribe_stream(audio, config):
            parts.append(p)
        return self._partials_to_result(parts, config, rid, audio)

    def _partials_to_result(
        self,
        parts: list[StreamPartial],
        config: ProviderConfig,
        result_id: str,
        audio: bytes,
    ) -> TranscriptionResult:
        if not parts:
            raise ProviderError("TRANSCRIBE_FAILED", "No partial results received", 500)

        text = self._streaming_final_text(parts)
        ttft_ms = None
        for p in parts:
            if p.text.strip():
                ttft_ms = p.timestamp_ms
                break

        total_ms = parts[-1].timestamp_ms
        duration_s = estimate_audio_duration_s(audio)
        confidences = [p.confidence for p in parts if p.confidence is not None]
        interim_hypotheses = group_interim_hypotheses([(p.text, p.is_final) for p in parts])
        revision = compute_partial_revision(interim_hypotheses, final_text=text)

        confidence = None
        if confidences:
            confidence = ConfidenceMetrics(
                mean=sum(confidences) / len(confidences),
                min=min(confidences),
                partial_revision_rate=revision.partial_revision_rate,
            )

        return TranscriptionResult(
            id=result_id,
            provider=config.provider,
            transport_mode="streaming",
            text=text,
            audio_duration_s=duration_s,
            timings=Timings(
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                rtf=total_ms / (duration_s * 1000) if duration_s > 0 else 0.0,
            ),
            cost_usd=self.estimate_cost_usd(duration_s, config),
            confidence=confidence,
            interim_hypotheses=interim_hypotheses,
        )

    @staticmethod
    def _streaming_final_text(parts: list[StreamPartial]) -> str:
        """Join segmented finals (e.g. Deepgram utterances) into one transcript."""
        finals = [p.text.strip() for p in parts if p.is_final and p.text.strip()]
        if finals:
            return " ".join(finals)
        for p in reversed(parts):
            if p.text.strip():
                return p.text.strip()
        return ""

    @abstractmethod
    def estimate_cost_usd(self, audio_duration_s: float, config: ProviderConfig) -> float:
        ...


def estimate_audio_duration_s(audio: bytes) -> float:
    """Best-effort audio duration from bytes."""
    duration = _duration_from_soundfile(audio)
    if duration is None and audio[:4] == b"RIFF":
        duration = _duration_from_wave(audio)
    if duration is None:
        # Fallback: assume ~128kbps compressed audio
        return max(len(audio) / 16000.0, 0.1)
    return duration


def _duration_from_soundfile(audio: bytes) -> float | None:
    try:
        import soundfile as sf
    except (ImportError, OSError):
        return None
    try:
        with sf.SoundFile(BytesIO(audio)) as handle:
            rate = float(handle.samplerate)
            if rate <= 0:
                return None
            return len(handle) / rate
    except (sf.SoundFileError, OSError, RuntimeError, ValueError, TypeError, EOFError):
        return None


def _duration_from_wave(audio: bytes) -> float | None:
    try:
        with wave.open(BytesIO(audio), "rb") as wf:
            rate = float(wf.getframerate())
            if rate <= 0:
                return None
            return wf.getnframes() / rate
    except (wave.Error, EOFError, OSError, RuntimeError, ValueError):
        return None


_REGISTRY: dict[str, type[STTProvider]] = {}


def register_provider(cls: type[STTProvider]) -> type[STTProvider]:
    _REGISTRY[cls.name] = cls
    return cls


def _ensure_providers_registered() -> None:
    if len(_REGISTRY) >= 4:
        return
    from stt_bench.providers.assemblyai import AssemblyAIProvider
    from stt_bench.providers.deepgram import DeepgramProvider
    from stt_bench.providers.mock import MockProvider
    from stt_bench.providers.whisper import WhisperProvider

    for cls in (MockProvider, WhisperProvider, DeepgramProvider, AssemblyAIProvider):
        register_provider(cls)


def get_provider(name: str, settings: Settings) -> STTProvider:
    _ensure_providers_registered()
    if name not in _REGISTRY:
        raise ProviderError("PROVIDER_NOT_FOUND", f"Unknown provider: {name}", 404)
    return _REGISTRY[name](settings)


def list_providers(settings: Settings) -> list[STTProvider]:
    _ensure_providers_registered()
    return [cls(settings) for cls in _REGISTRY.values()]
