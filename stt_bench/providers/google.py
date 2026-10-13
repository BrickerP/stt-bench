"""Google Cloud Speech-to-Text batch provider (v1 REST).

CI and unit tests must not call the live API. Use the mock provider or contract tests.
Manual smoke: set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON and
run a single-file transcribe locally.

``speech:recognize`` requires an OAuth bearer token (cloud-platform scope).
This adapter mints that token from the service account file with google-auth
and posts audio with httpx. It does not use an API key and does not import
google-cloud-speech.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from google.auth.exceptions import GoogleAuthError, TransportError
from google.oauth2 import service_account

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
from stt_bench.settings import Settings

_SPEECH_ROOT = "https://speech.googleapis.com/v1"
_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SYNC_MAX_S = 60.0
_MAX_INLINE_BYTES = 10 * 1024 * 1024
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


def credentials_path(settings: Settings) -> Path:
    """Resolve GOOGLE_APPLICATION_CREDENTIALS. Local filesystem only."""
    raw = getattr(settings, "google_application_credentials", None)
    text = str(raw).strip() if raw else ""
    if not text:
        raise ProviderError(
            "PROVIDER_AUTH_FAILED",
            "GOOGLE_APPLICATION_CREDENTIALS not configured",
            401,
        )
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = settings.resolve_path(text)
    if not path.is_file():
        raise ProviderError(
            "PROVIDER_AUTH_FAILED",
            f"GOOGLE_APPLICATION_CREDENTIALS file not found: {path}",
            401,
        )
    return path


def _bcp47(language: str | None) -> str:
    lang = (language or "en").strip().replace("_", "-")
    if not lang:
        return "en-US"
    if "-" in lang:
        primary, region, *_rest = lang.split("-")
        return f"{primary.lower()}-{region.upper()}"
    return _LANG_REGION.get(lang.lower(), lang)


def _container(audio: bytes) -> str:
    if audio[:4] == b"RIFF":
        return "wav"
    if audio[:4] == b"fLaC":
        return "flac"
    if audio[:4] == b"OggS":
        return "ogg"
    if audio[:3] == b"ID3" or _looks_like_mp3(audio):
        return "mp3"
    return "pcm"


def _looks_like_mp3(audio: bytes) -> bool:
    return len(audio) > 1 and audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0


def _recognition_config(audio: bytes, language: str, model: str) -> dict:
    """v1 RecognitionConfig. WAV/FLAC keep their headers; other bytes set encoding."""
    config: dict = {
        "languageCode": _bcp47(language),
        "enableAutomaticPunctuation": True,
        "enableWordTimeOffsets": True,
    }
    if model and model != "default":
        config["model"] = model
    kind = _container(audio)
    if kind == "mp3":
        config["encoding"] = "MP3"
    elif kind == "ogg":
        config["encoding"] = "OGG_OPUS"
    elif kind == "pcm":
        config["encoding"] = "LINEAR16"
        config["sampleRateHertz"] = 16000
    return config


def _account_info(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderError(
            "PROVIDER_AUTH_FAILED",
            f"GOOGLE_APPLICATION_CREDENTIALS is not valid JSON: {path}",
            401,
        ) from exc
    if not isinstance(raw, dict):
        raise ProviderError(
            "PROVIDER_AUTH_FAILED",
            "GOOGLE_APPLICATION_CREDENTIALS must be a service account JSON object",
            401,
        )
    if raw.get("type") not in (None, "service_account"):
        raise ProviderError(
            "PROVIDER_AUTH_FAILED",
            "GOOGLE_APPLICATION_CREDENTIALS must be a service account JSON key",
            401,
        )
    if not raw.get("client_email") or not raw.get("private_key"):
        raise ProviderError(
            "PROVIDER_AUTH_FAILED",
            "GOOGLE_APPLICATION_CREDENTIALS must include client_email and private_key",
            401,
        )
    info = dict(raw)
    info.setdefault("token_uri", _TOKEN_URI)
    return info


def _seconds(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    text = text.removesuffix("s")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _http_error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return resp.text[:200]
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:300]
    return resp.text[:200]


def _raise_for_status(resp: httpx.Response, action: str) -> None:
    if resp.status_code < 400:
        return
    detail = _http_error_text(resp)
    if resp.status_code in (401, 403):
        raise ProviderError(
            "PROVIDER_AUTH_FAILED",
            f"Google Speech auth failed during {action}: {detail}",
            401,
        )
    raise ProviderError(
        "PROVIDER_UPSTREAM_ERROR",
        f"Google Speech {action} failed: {resp.status_code} {detail}",
        502,
    )


def _operation_url(name: str) -> str:
    if name.startswith("https://"):
        return name
    name = name.lstrip("/")
    if name.startswith("v1/"):
        return f"https://speech.googleapis.com/{name}"
    if name.startswith("operations/"):
        return f"{_SPEECH_ROOT}/{name}"
    return f"{_SPEECH_ROOT}/operations/{name}"


def _extract_results(body: dict) -> list:
    results = body.get("results")
    if isinstance(results, list):
        return results
    response = body.get("response")
    if isinstance(response, dict) and isinstance(response.get("results"), list):
        return response["results"]
    return []


def _operation_error(body: dict) -> str | None:
    err = body.get("error")
    if not err:
        return None
    if isinstance(err, dict):
        return str(err.get("message") or err)[:300]
    return str(err)[:300]


def _parse_results(results: list) -> tuple[str, list[float], list[WordTimestamp]]:
    texts: list[str] = []
    confidences: list[float] = []
    words: list[WordTimestamp] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        alts = result.get("alternatives") or []
        if not alts or not isinstance(alts[0], dict):
            continue
        alt = alts[0]
        transcript = (alt.get("transcript") or "").strip()
        if transcript:
            texts.append(transcript)
        if alt.get("confidence") is not None:
            confidences.append(float(alt["confidence"]))
        for word in alt.get("words") or []:
            if not isinstance(word, dict):
                continue
            token = (word.get("word") or "").strip()
            if not token:
                continue
            words.append(
                WordTimestamp(
                    word=token,
                    start_s=_seconds(word.get("startTime")),
                    end_s=_seconds(word.get("endTime")),
                )
            )
    return " ".join(texts), confidences, words


class _TokenResponse:
    def __init__(self, response: httpx.Response):
        self.status = response.status_code
        self.headers = {key.lower(): value for key, value in response.headers.items()}
        self.data = response.content


class _TokenRequest:
    """google-auth transport.Request backed by httpx. No ``requests`` dependency."""

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        del kwargs
        try:
            with httpx.Client(timeout=timeout or 30.0) as client:
                response = client.request(method, url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise TransportError(str(exc)) from exc
        return _TokenResponse(response)


@register_provider
class GoogleProvider(STTProvider):
    name = "google"
    display_name = "Google Cloud Speech-to-Text"
    capabilities = ProviderCapabilities(
        supports_batch=True,
        supports_streaming=False,
        supports_confidence=True,
        supports_word_timestamps=True,
    )

    async def validate_config(self, config: ProviderConfig) -> None:
        info = _account_info(credentials_path(self.settings))
        try:
            service_account.Credentials.from_service_account_info(info, scopes=[_SCOPE])
        except (GoogleAuthError, ValueError) as exc:
            raise ProviderError(
                "PROVIDER_AUTH_FAILED",
                "GOOGLE_APPLICATION_CREDENTIALS is not a usable service account key",
                401,
            ) from exc

    def _auth_headers(self) -> dict[str, str]:
        info = _account_info(credentials_path(self.settings))
        try:
            creds = service_account.Credentials.from_service_account_info(info, scopes=[_SCOPE])
            creds.refresh(_TokenRequest())
        except (GoogleAuthError, ValueError) as exc:
            raise ProviderError(
                "PROVIDER_AUTH_FAILED",
                "GOOGLE_APPLICATION_CREDENTIALS token exchange failed",
                401,
            ) from exc
        if not creds.token:
            raise ProviderError(
                "PROVIDER_AUTH_FAILED",
                "GOOGLE_APPLICATION_CREDENTIALS token exchange failed",
                401,
            )
        headers = {"Authorization": f"Bearer {creds.token}"}
        project = creds.project_id or info.get("project_id")
        if project:
            headers["x-goog-user-project"] = str(project)
        return headers

    async def transcribe_batch(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> TranscriptionResult:
        if len(audio) > _MAX_INLINE_BYTES:
            raise ProviderError(
                "AUDIO_INVALID",
                "Google Speech inline audio is limited to 10 MB; "
                "this adapter does not upload to Cloud Storage",
                422,
            )
        duration_s = estimate_audio_duration_s(audio)
        long_running = duration_s > _SYNC_MAX_S
        headers = await asyncio.to_thread(self._auth_headers)
        payload = {
            "config": _recognition_config(audio, config.language, config.model),
            "audio": {"content": base64.b64encode(audio).decode("ascii")},
        }
        method = "longrunningrecognize" if long_running else "recognize"
        start = time.perf_counter()
        operation_name: str | None = None

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{_SPEECH_ROOT}/speech:{method}",
                headers=headers,
                json=payload,
            )
            _raise_for_status(resp, method)
            body = resp.json()
            if not isinstance(body, dict):
                raise ProviderError(
                    "PROVIDER_UPSTREAM_ERROR",
                    "Google Speech returned a non-object response",
                    502,
                )
            if long_running:
                err = _operation_error(body)
                if err:
                    raise ProviderError(
                        "PROVIDER_UPSTREAM_ERROR",
                        f"Google Speech transcription error: {err}",
                        502,
                    )
                if not body.get("done"):
                    operation_name = body.get("name")
                    if not operation_name:
                        raise ProviderError(
                            "PROVIDER_UPSTREAM_ERROR",
                            "Google Speech long-running recognize returned no operation name",
                            502,
                        )
                    body = await self._poll_operation(client, headers, str(operation_name))
                else:
                    operation_name = body.get("name")

        results = _extract_results(body)
        text, confidences, words = _parse_results(results)
        total_ms = (time.perf_counter() - start) * 1000
        confidence = None
        if confidences:
            confidence = ConfidenceMetrics(
                mean=sum(confidences) / len(confidences),
                min=min(confidences),
            )
        raw: dict = {"result_count": len(results), "long_running": long_running}
        if operation_name:
            raw["operation"] = operation_name
        return TranscriptionResult(
            id=f"tr_{uuid.uuid4().hex[:12]}",
            provider="google",
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
            raw_provider_response=raw,
        )

    async def _poll_operation(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        name: str,
    ) -> dict:
        url = _operation_url(name)
        for _ in range(120):
            resp = await client.get(url, headers=headers)
            _raise_for_status(resp, "poll")
            body = resp.json()
            if not isinstance(body, dict):
                raise ProviderError(
                    "PROVIDER_UPSTREAM_ERROR",
                    "Google Speech poll returned a non-object response",
                    502,
                )
            err = _operation_error(body)
            if err:
                raise ProviderError(
                    "PROVIDER_UPSTREAM_ERROR",
                    f"Google Speech transcription error: {err}",
                    502,
                )
            if body.get("done"):
                return body
            await asyncio.sleep(1.0)
        raise ProviderError(
            "PROVIDER_UPSTREAM_ERROR",
            "Google Speech transcription timed out",
            502,
        )

    async def transcribe_stream(
        self,
        audio: bytes,
        config: ProviderConfig,
    ) -> AsyncIterator[StreamPartial]:
        raise TransportNotSupported("google", "streaming")
        yield  # pragma: no cover

    def estimate_cost_usd(self, audio_duration_s: float, config: ProviderConfig) -> float:
        return estimate_provider_cost("google", config.model, audio_duration_s, self.settings)

    def default_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider="google",
            model=getattr(self.settings, "google_speech_model", "latest_long"),
            language="en",
            transport_mode="batch",
        )
