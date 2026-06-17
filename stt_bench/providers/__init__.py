"""STT provider adapters."""

from stt_bench.providers.base import (
    ProviderError,
    STTProvider,
    StreamPartial,
    TransportNotSupported,
    get_provider,
    list_providers,
)
from stt_bench.providers.deepgram import DeepgramProvider
from stt_bench.providers.mock import MockProvider
from stt_bench.providers.whisper import WhisperProvider

__all__ = [
    "DeepgramProvider",
    "MockProvider",
    "ProviderError",
    "STTProvider",
    "StreamPartial",
    "TransportNotSupported",
    "WhisperProvider",
    "get_provider",
    "list_providers",
]
