"""Azure Speech batch provider (fast transcription REST).

CI and unit tests must not call the live API. Use the mock provider or contract tests.
Manual smoke: set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION and run a single-file
transcribe locally.

Calls ``transcriptions:transcribe`` (sync fast transcription) with httpx.
Streaming is not implemented.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import AsyncIterator

import httpx

from stt_bench.metrics.cost import estimate_provider_cost
from stt_bench.models.config import ProviderCapabilities, ProviderConfig
from stt_bench.models.transcription import (
    ConfidenceMetrics,
    Timings,
    TranscriptionResult,
    WordTimestamp,
)
from stt_bench.providers.base import (
    ProviderError,
    StreamPartial,
    STTProvider,
    TransportNotSupported,
    estimate_audio_duration_s,
    register_provider,
)

_API_VERSION = "2025-10-15"
_REGION_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_LANG_REGION = {
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "pt": "pt-BR",
    "it": "it-IT",
    "nl": "nl-NL",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "zh": "zh-CN",
}


def _bcp47(language: str | None) -> str:
    lang = (language or "en").strip().replace("_", "-")
    if not lang:
        return "en-US"
    if "-" in lang:
        primary, region, *_rest = lang.split("-")
        return f"{primary.lower()}-{region.upper()}"
    return _LANG_REGION.get(lang.lower(), lang)


def _audio_part(audio: bytes) -> tuple[str, str]:
    if audio[:4] == b"RIFF":
        return "audio.wav", "audio/wav"
    if audio[:4] == b"fLaC":
        return "audio.flac", "audio/flac"
    if audio[:4] == b"OggS":
        return "audio.ogg", "audio/ogg"
    if audio[:3] == b"ID3" or (len(audio) > 1 and audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0):
        return "audio.mp3", "audio/mpeg"
    return "audio.wav", "audio/wav"


def _endpoint(region: str) -> str:
    return (
        f"https://{region}.api.cognitive.microsoft.com"
        f"/speechtotext/transcriptions:transcribe?api-version={_API_VERSION}"
    )


def _error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return resp.text[:200]
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:300]
    return resp.text[:200]


def _parse_body(body: dict) -> tuple[str, list[float], list[WordTimestamp]]:
    texts: list[str] = []
    for phrase in body.get("combinedPhrases") or []:
        if isinstance(phrase, dict):
            text = (phrase.get("text") or "").strip()
            if text:
                texts.append(text)
    confidences: list[float] = []
    words: list[WordTimestamp] = []
    phrase_texts: list[str] = []
    for phrase in body.get("phrases") or []:
        if not isinstance(phrase, dict):
            continue
        text = (phrase.get("text") or "").strip()
        if text:
            phrase_texts.append(text)
        if phrase.get("confidence") is not None:
            confidences.append(float(phrase["confidence"]))
        for word in phrase.get("words") or []:
            if not isinstance(word, dict):
                continue
            token = (word.get("text") or word.get("word") or "").strip()
            if not token:
                continue
            offset_ms = float(word.get("offsetMilliseconds") or 0)
            dur_ms = float(word.get("durationMilliseconds") or 0)
            words.append(
                WordTimestamp(
                    word=token,
                    start_s=offset_ms / 1000.0,
                    end_s=(offset_ms + dur_ms) / 1000.0,
                )
            )
    if not texts:
        texts = phrase_texts
    return " ".join(texts), confidences, words


@register_provider
class AzureProvider(STTProvider):
    name = "azure"
    display_name = "Azure Speech"
    capabilities = ProviderCapabilities(
        supports_batch=True,
        supports_streaming=False,
        supports_confidence=True,
        supports_word_timestamps=True,
    )

    def _require_credentials(self) -> tuple[str, str]:
        key = (getattr(self.settings, "azure_speech_key", None) or "").strip()
        region = (getattr(self.settings, "azure_speech_region", None) or "").strip().lower()
        missing: list[str] = []
        if not key:
            missing.append("AZURE_SPEECH_KEY")
        if not region:
            missing.append("AZURE_SPEECH_REGION")
        if missing:
            raise ProviderError(
                "PROVIDER_AUTH_FAILED",
                f"{' and '.join(missing)} not configured",
                401,
            )
        if not _REGION_RE.fullmatch(region):
            raise ProviderError(
                "PROVIDER_AUTH_FAILED",
                "AZURE_SPEECH_REGION is not a valid region name",
                401,
            )
        return key, region

    async def validate_config(self, config: ProviderConfig) -> None:
        self._require_credentials()

    async def transcribe_batch(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> TranscriptionResult:
        key, region = self._require_credentials()
        duration_s = estimate_audio_duration_s(audio)
        filename, mime = _audio_part(audio)
        definition = json.dumps({"locales": [_bcp47(config.language)]})
        start = time.perf_counter()

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                _endpoint(region),
                headers={
                    "Ocp-Apim-Subscription-Key": key,
                    "Accept": "application/json",
                },
                data={"definition": definition},
                files={"audio": (filename, audio, mime)},
            )
        if resp.status_code in (401, 403):
            raise ProviderError(
                "PROVIDER_AUTH_FAILED",
                f"Azure Speech auth failed: {_error_text(resp)}",
                401,
            )
        if resp.status_code >= 400:
            raise ProviderError(
                "PROVIDER_UPSTREAM_ERROR",
                f"Azure Speech transcribe failed: {resp.status_code} {_error_text(resp)}",
                502,
            )
        try:
            body = resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "PROVIDER_UPSTREAM_ERROR",
                "Azure Speech returned a non-JSON body",
                502,
            ) from exc
        if not isinstance(body, dict):
            raise ProviderError(
                "PROVIDER_UPSTREAM_ERROR",
                "Azure Speech returned a non-object response",
                502,
            )

        text, confidences, words = _parse_body(body)
        total_ms = (time.perf_counter() - start) * 1000
        confidence = None
        if confidences:
            confidence = ConfidenceMetrics(
                mean=sum(confidences) / len(confidences),
                min=min(confidences),
            )
        return TranscriptionResult(
            id=f"tr_{uuid.uuid4().hex[:12]}",
            provider="azure",
            transport_mode="batch",
            text=text,
            audio_duration_s=duration_s,
            timings=Timings(
                ttft_ms=None,
                total_ms=total_ms,
                rtf=total_ms / (duration_s * 1000) if duration_s > 0 else 0.0,
            ),
            cost_usd=self.estimate_cost_usd(duration_s, config),
            confidence=confidence,
            word_timestamps=words or None,
            cache_hit=False,
            raw_provider_response={
                "phrase_count": len(body.get("phrases") or []),
                "durationMilliseconds": body.get("durationMilliseconds"),
            },
        )

    async def transcribe_stream(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> AsyncIterator[StreamPartial]:
        raise TransportNotSupported("azure", "streaming")
        yield  # pragma: no cover

    def estimate_cost_usd(self, audio_duration_s: float, config: ProviderConfig) -> float:
        return estimate_provider_cost("azure", config.model, audio_duration_s, self.settings)

    def default_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider="azure",
            model=getattr(self.settings, "azure_speech_model", "fast"),
            language="en",
            transport_mode="batch",
        )
