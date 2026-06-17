"""Tests for mock STT provider."""

import pytest

from stt_bench.models.config import ProviderConfig
from stt_bench.providers.mock import MockProvider
from stt_bench.settings import get_settings


@pytest.fixture
def mock_provider():
    return MockProvider(get_settings())


@pytest.mark.asyncio
async def test_mock_batch_transcription(mock_provider):
    config = ProviderConfig(
        provider="mock",
        model="mock-v1",
        transport_mode="batch",
        extra={"reference_text": "hello world", "latency_ms": 1},
    )
    result = await mock_provider.transcribe_batch(b"fake audio", config)
    assert result.text == "hello world"
    assert result.timings.ttft_ms is None
    assert result.transport_mode == "batch"


@pytest.mark.asyncio
async def test_mock_streaming_transcription(mock_provider):
    config = ProviderConfig(
        provider="mock",
        model="mock-v1",
        transport_mode="streaming",
        extra={"reference_text": "one two three", "latency_ms": 1},
    )
    parts = []
    async for p in mock_provider.transcribe_stream(b"fake", config):
        parts.append(p)
    assert len(parts) >= 1
    assert parts[-1].is_final
    assert "three" in parts[-1].text
