import base64
import json

import httpx
import pytest

from stt_bench.models.config import ProviderCapabilities, ProviderConfig
from stt_bench.providers.base import (
    ProviderError,
    TransportNotSupported,
    get_provider,
    list_providers,
)
from stt_bench.providers.google import GoogleProvider, _recognition_config, credentials_path
from stt_bench.settings import Settings


def test_google_registered():
    names = {p.name for p in list_providers(Settings())}
    assert "google" in names
    assert "mock" in names


def test_registry_gate_includes_google_and_azure():
    from stt_bench.providers import base

    saved = dict(base._REGISTRY)
    try:
        base._REGISTRY.clear()
        names = {p.name for p in base.list_providers(Settings())}
    finally:
        base._REGISTRY.clear()
        base._REGISTRY.update(saved)
    assert {"mock", "whisper", "deepgram", "assemblyai", "google", "azure"} <= names


def test_google_capabilities_contract():
    p = GoogleProvider(Settings())
    assert p.name == "google"
    assert p.display_name == "Google Cloud Speech-to-Text"
    assert isinstance(p.capabilities, ProviderCapabilities)
    assert p.capabilities.supports_batch is True
    assert p.capabilities.supports_streaming is False
    cfg = p.default_config()
    assert cfg.provider == "google"
    assert cfg.model == "latest_long"
    assert cfg.transport_mode == "batch"
    assert p.estimate_cost_usd(60, cfg) == pytest.approx(0.016)


def test_google_wav_config_lets_vendor_read_header():
    cfg = _recognition_config(b"RIFF", "en", "latest_long")
    assert cfg["languageCode"] == "en-US"
    assert cfg["model"] == "latest_long"
    assert "encoding" not in cfg


def test_get_provider_google():
    assert get_provider("google", Settings()).name == "google"


@pytest.mark.asyncio
async def test_google_streaming_rejected(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("stt_bench.providers.google.httpx.AsyncClient", _boom)
    monkeypatch.setattr("stt_bench.providers.google.httpx.Client", _boom)
    p = GoogleProvider(Settings())
    cfg = ProviderConfig(provider="google", model="latest_long", transport_mode="streaming")
    with pytest.raises(TransportNotSupported):
        async for _ in p.transcribe_stream(b"RIFF", cfg):
            pass


@pytest.mark.asyncio
async def test_google_validate_requires_credentials(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("stt_bench.providers.google.httpx.AsyncClient", _boom)
    monkeypatch.setattr("stt_bench.providers.google.httpx.Client", _boom)
    p = GoogleProvider(Settings(google_application_credentials=None))
    cfg = ProviderConfig(provider="google", model="latest_long")
    with pytest.raises(ProviderError) as exc:
        await p.validate_config(cfg)
    assert "GOOGLE_APPLICATION_CREDENTIALS" in str(exc.value)


@pytest.mark.asyncio
async def test_google_validate_rejects_non_service_account(monkeypatch, tmp_path):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("stt_bench.providers.google.httpx.AsyncClient", _boom)
    monkeypatch.setattr("stt_bench.providers.google.httpx.Client", _boom)
    path = tmp_path / "sa.json"
    path.write_text('{"type": "authorized_user"}', encoding="utf-8")
    p = GoogleProvider(Settings(google_application_credentials=str(path)))
    cfg = ProviderConfig(provider="google", model="latest_long")
    with pytest.raises(ProviderError) as exc:
        await p.validate_config(cfg)
    assert "GOOGLE_APPLICATION_CREDENTIALS" in str(exc.value)


def test_google_missing_file_names_env(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(ProviderError) as exc:
        credentials_path(Settings(google_application_credentials=str(missing)))
    assert "GOOGLE_APPLICATION_CREDENTIALS" in str(exc.value)


def _pem() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _service_account_file(tmp_path, private_key: str):
    path = tmp_path / "sa.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "demo-project",
                "private_key": private_key,
                "client_email": "bench@demo-project.iam.gserviceaccount.com",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_google_token_exchange_is_local(monkeypatch, tmp_path):
    path = _service_account_file(tmp_path, _pem())
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={"access_token": "ya29.test", "expires_in": 3600, "token_type": "Bearer"},
        )

    transport = httpx.MockTransport(handler)

    class _Client(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("stt_bench.providers.google.httpx.Client", _Client)
    headers = GoogleProvider(Settings(google_application_credentials=str(path)))._auth_headers()
    assert headers["Authorization"] == "Bearer ya29.test"
    assert headers["x-goog-user-project"] == "demo-project"
    assert "oauth2.googleapis.com/token" in seen["url"]
    assert "grant_type=" in seen["body"]
    assert "assertion=" in seen["body"]
    assert "PRIVATE KEY" not in seen["body"]


def _patch_async_client(monkeypatch, handler):
    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("stt_bench.providers.google.httpx.AsyncClient", _Client)


@pytest.mark.asyncio
async def test_google_batch_posts_recognize(monkeypatch):
    audio = b"RIFF" + b"\x00" * 32
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        assert "key" not in request.url.params
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "alternatives": [
                            {
                                "transcript": "hello world",
                                "confidence": 0.5,
                                "words": [
                                    {"word": "hello", "startTime": "0s", "endTime": "0.500s"},
                                    {"word": "world", "startTime": "0.500s", "endTime": "1s"},
                                ],
                            }
                        ]
                    }
                ]
            },
        )

    _patch_async_client(monkeypatch, handler)
    p = GoogleProvider(Settings(google_application_credentials=None))
    monkeypatch.setattr(
        p,
        "_auth_headers",
        lambda: {"Authorization": "Bearer test-token", "x-goog-user-project": "demo"},
    )
    cfg = ProviderConfig(provider="google", model="latest_long", language="en")
    result = await p.transcribe_batch(audio, cfg)
    assert seen["path"].endswith("/speech:recognize")
    assert seen["auth"] == "Bearer test-token"
    assert seen["body"]["config"]["languageCode"] == "en-US"
    assert seen["body"]["config"]["model"] == "latest_long"
    assert "encoding" not in seen["body"]["config"]
    assert base64.b64decode(seen["body"]["audio"]["content"]) == audio
    assert result.text == "hello world"
    assert result.provider == "google"
    assert result.transport_mode == "batch"
    assert result.confidence is not None
    assert result.confidence.mean == pytest.approx(0.5)
    assert result.word_timestamps is not None
    assert [w.word for w in result.word_timestamps] == ["hello", "world"]


@pytest.mark.asyncio
async def test_google_long_audio_polls_operation(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith(":longrunningrecognize"):
            return httpx.Response(200, json={"name": "operations/op1"})
        if request.url.path.endswith("/operations/op1"):
            return httpx.Response(
                200,
                json={
                    "done": True,
                    "response": {
                        "results": [{"alternatives": [{"transcript": "long hello", "confidence": 0.8}]}]
                    },
                },
            )
        return httpx.Response(500, json={"error": {"message": "unexpected"}})

    async def _no_sleep(_seconds: float) -> None:
        return None

    _patch_async_client(monkeypatch, handler)
    monkeypatch.setattr("stt_bench.providers.google.estimate_audio_duration_s", lambda _audio: 90.0)
    monkeypatch.setattr("stt_bench.providers.google.asyncio.sleep", _no_sleep)
    p = GoogleProvider(Settings())
    monkeypatch.setattr(p, "_auth_headers", lambda: {"Authorization": "Bearer test-token"})
    cfg = ProviderConfig(provider="google", model="latest_long")
    result = await p.transcribe_batch(b"RIFF", cfg)
    assert calls[0].endswith(":longrunningrecognize")
    assert calls[1].endswith("/operations/op1")
    assert result.text == "long hello"
    assert result.raw_provider_response["long_running"] is True
    assert result.raw_provider_response["operation"] == "operations/op1"
