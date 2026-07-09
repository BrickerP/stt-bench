"""Provider configuration models."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TransportMode(str, Enum):
    BATCH = "batch"
    STREAMING = "streaming"


class ProviderCapabilities(BaseModel):
    supports_batch: bool
    supports_streaming: bool
    supports_confidence: bool
    supports_word_timestamps: bool


class ProviderConfig(BaseModel):
    provider: Literal["whisper", "deepgram", "mock", "assemblyai"]
    model: str
    language: str = "en"
    transport_mode: Literal["batch", "streaming"] = "batch"
    extra: dict[str, Any] = Field(default_factory=dict)

    def config_hash_input(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "language": self.language,
            "transport_mode": self.transport_mode,
            "extra": self.extra,
        }
