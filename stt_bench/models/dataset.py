"""Dataset manifest models."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class SampleRecord(BaseModel):
    id: str
    audio_path: str
    reference_text: str
    condition: Literal["clean", "noisy"]
    source: Literal["librispeech", "synthetic"]
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetManifest(BaseModel):
    dataset_id: str
    name: str
    description: str = ""
    samples: list[SampleRecord]
