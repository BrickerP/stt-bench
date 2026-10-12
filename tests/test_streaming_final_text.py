"""Tests for streaming transcript assembly."""

from stt_bench.providers.base import StreamPartial, STTProvider


class _StubProvider(STTProvider):
    name = "stub"
    display_name = "Stub"
    capabilities = None  # type: ignore

    async def validate_config(self, config):
        pass

    async def transcribe_batch(self, audio, config):
        raise NotImplementedError

    async def transcribe_stream(self, audio, config):
        yield StreamPartial(text="", is_final=True, timestamp_ms=0)

    def estimate_cost_usd(self, audio_duration_s, config):
        return 0.0


def test_streaming_final_text_joins_segmented_finals():
    provider = _StubProvider(None)  # type: ignore
    parts = [
        StreamPartial(text="hello world", is_final=False, timestamp_ms=10),
        StreamPartial(text="hello world", is_final=True, timestamp_ms=100),
        StreamPartial(text="goodbye", is_final=True, timestamp_ms=200),
        StreamPartial(text="", is_final=True, timestamp_ms=300),
    ]
    assert provider._streaming_final_text(parts) == "hello world goodbye"


def test_streaming_final_text_falls_back_to_last_non_empty():
    provider = _StubProvider(None)  # type: ignore
    parts = [
        StreamPartial(text="partial only", is_final=False, timestamp_ms=50),
        StreamPartial(text="", is_final=True, timestamp_ms=100),
    ]
    assert provider._streaming_final_text(parts) == "partial only"
