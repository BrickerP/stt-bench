import pytest

from stt_bench.models.config import ProviderCapabilities, ProviderConfig
from stt_bench.providers.assemblyai import AssemblyAIProvider
from stt_bench.providers.base import TransportNotSupported, get_provider, list_providers
from stt_bench.settings import Settings


def test_assemblyai_registered():
    settings = Settings()
    names = {p.name for p in list_providers(settings)}
    assert "assemblyai" in names
    assert "mock" in names


def test_assemblyai_capabilities_contract():
    p = AssemblyAIProvider(Settings())
    assert p.name == "assemblyai"
    assert isinstance(p.capabilities, ProviderCapabilities)
    assert p.capabilities.supports_batch is True
    assert p.capabilities.supports_streaming is False
    cfg = p.default_config()
    assert cfg.provider == "assemblyai"
    assert cfg.transport_mode == "batch"


@pytest.mark.asyncio
async def test_assemblyai_streaming_rejected():
    p = AssemblyAIProvider(Settings())
    cfg = ProviderConfig(provider="assemblyai", model="best", transport_mode="streaming")
    with pytest.raises(TransportNotSupported):
        async for _ in p.transcribe_stream(b"RIFF", cfg):
            pass


@pytest.mark.asyncio
async def test_assemblyai_validate_requires_key():
    p = AssemblyAIProvider(Settings(assemblyai_api_key=None))
    cfg = ProviderConfig(provider="assemblyai", model="best")
    with pytest.raises(Exception) as exc:
        await p.validate_config(cfg)
    assert "ASSEMBLYAI_API_KEY" in str(exc.value)


def test_get_provider_assemblyai():
    p = get_provider("assemblyai", Settings())
    assert p.name == "assemblyai"
