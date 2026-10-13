import httpx
import pytest

from stt_bench.models.config import ProviderCapabilities, ProviderConfig
from stt_bench.providers.azure import AzureProvider
from stt_bench.providers.base import (
    ProviderError,
    TransportNotSupported,
    get_provider,
    list_providers,
)
from stt_bench.settings import Settings

_KEY = "a" * 32


def test_azure_registered():
    names = {p.name for p in list_providers(Settings())}
    assert "azure" in names
    assert "mock" in names


def test_azure_capabilities_contract():
    p = AzureProvider(Settings())
    assert p.name == "azure"
    assert p.display_name == "Azure Speech"
    assert isinstance(p.capabilities, ProviderCapabilities)
    assert p.capabilities.supports_batch is True
    assert p.capabilities.supports_streaming is False
    cfg = p.default_config()
    assert cfg.provider == "azure"
    assert cfg.model == "fast"
    assert cfg.transport_mode == "batch"
    assert p.estimate_cost_usd(60, cfg) == pytest.approx(0.0167)


def test_get_provider_azure():
    assert get_provider("azure", Settings()).name == "azure"


@pytest.mark.asyncio
async def test_azure_streaming_rejected(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("stt_bench.providers.azure.httpx.AsyncClient", _boom)
    p = AzureProvider(Settings())
    cfg = ProviderConfig(provider="azure", model="fast", transport_mode="streaming")
    with pytest.raises(TransportNotSupported):
        async for _ in p.transcribe_stream(b"RIFF", cfg):
            pass


@pytest.mark.asyncio
async def test_azure_validate_requires_key_and_region(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("stt_bench.providers.azure.httpx.AsyncClient", _boom)
    p = AzureProvider(Settings(azure_speech_key=None, azure_speech_region=None))
    cfg = ProviderConfig(provider="azure", model="fast")
    with pytest.raises(ProviderError) as exc:
        await p.validate_config(cfg)
    assert "AZURE_SPEECH_KEY" in str(exc.value)
    assert "AZURE_SPEECH_REGION" in str(exc.value)


@pytest.mark.asyncio
async def test_azure_validate_requires_region_when_key_set(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("stt_bench.providers.azure.httpx.AsyncClient", _boom)
    p = AzureProvider(Settings(azure_speech_key=_KEY, azure_speech_region=None))
    cfg = ProviderConfig(provider="azure", model="fast")
    with pytest.raises(ProviderError) as exc:
        await p.validate_config(cfg)
    message = str(exc.value)
    assert "AZURE_SPEECH_REGION" in message
    assert "AZURE_SPEECH_KEY" not in message


@pytest.mark.asyncio
async def test_azure_validate_rejects_bad_region(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("stt_bench.providers.azure.httpx.AsyncClient", _boom)
    p = AzureProvider(Settings(azure_speech_key=_KEY, azure_speech_region="not a region"))
    cfg = ProviderConfig(provider="azure", model="fast")
    with pytest.raises(ProviderError) as exc:
        await p.validate_config(cfg)
    assert "AZURE_SPEECH_REGION" in str(exc.value)


@pytest.mark.asyncio
async def test_azure_validate_accepts_region_without_network(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr("stt_bench.providers.azure.httpx.AsyncClient", _boom)
    p = AzureProvider(Settings(azure_speech_key=_KEY, azure_speech_region="EastUS"))
    await p.validate_config(ProviderConfig(provider="azure", model="fast"))


@pytest.mark.asyncio
async def test_azure_batch_posts_fast_transcription(monkeypatch):
    audio = b"RIFF" + b"\x00" * 16
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["ocp-apim-subscription-key"]
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "durationMilliseconds": 500,
                "combinedPhrases": [{"text": "hello world"}],
                "phrases": [
                    {
                        "text": "hello world",
                        "confidence": 0.75,
                        "words": [
                            {"text": "hello", "offsetMilliseconds": 0, "durationMilliseconds": 200},
                            {"text": "world", "offsetMilliseconds": 200, "durationMilliseconds": 300},
                        ],
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("stt_bench.providers.azure.httpx.AsyncClient", _Client)
    p = AzureProvider(Settings(azure_speech_key=_KEY, azure_speech_region="eastus"))
    cfg = ProviderConfig(provider="azure", model="fast", language="en")
    result = await p.transcribe_batch(audio, cfg)
    assert seen["url"].startswith(
        "https://eastus.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?"
    )
    assert "api-version=2025-10-15" in seen["url"]
    assert seen["key"] == _KEY
    assert b"en-US" in seen["body"]
    assert audio in seen["body"]
    assert result.text == "hello world"
    assert result.provider == "azure"
    assert result.transport_mode == "batch"
    assert result.confidence is not None
    assert result.confidence.mean == pytest.approx(0.75)
    assert result.word_timestamps is not None
    assert result.word_timestamps[1].start_s == pytest.approx(0.2)
    assert result.word_timestamps[1].end_s == pytest.approx(0.5)
