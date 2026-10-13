"""STT provider adapters."""

from stt_bench.providers.assemblyai import AssemblyAIProvider
from stt_bench.providers.azure import AzureProvider
from stt_bench.providers.base import (
    ProviderError,
    StreamPartial,
    STTProvider,
    TransportNotSupported,
    get_provider,
    list_providers,
)
from stt_bench.providers.deepgram import DeepgramProvider
from stt_bench.providers.google import GoogleProvider
from stt_bench.providers.mock import MockProvider
from stt_bench.providers.whisper import WhisperProvider

__all__ = [
    "AssemblyAIProvider",
    "AzureProvider",
    "DeepgramProvider",
    "GoogleProvider",
    "MockProvider",
    "ProviderError",
    "STTProvider",
    "StreamPartial",
    "TransportNotSupported",
    "WhisperProvider",
    "get_provider",
    "list_providers",
]
