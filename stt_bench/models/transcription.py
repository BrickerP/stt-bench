"""Transcription result models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Timings(BaseModel):
    ttft_ms: float | None = None
    total_ms: float
    rtf: float


class ConfidenceMetrics(BaseModel):
    mean: float | None = None
    min: float | None = None
    partial_revision_rate: float | None = None


class WordTimestamp(BaseModel):
    word: str
    start_s: float
    end_s: float


class TranscriptionResult(BaseModel):
    id: str
    provider: str
    transport_mode: Literal["batch", "streaming"]
    text: str
    audio_duration_s: float
    timings: Timings
    cost_usd: float | None = None
    confidence: ConfidenceMetrics | None = None
    word_timestamps: list[WordTimestamp] | None = None
    cache_hit: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    raw_provider_response: dict | None = None


class LeaderboardEntry(BaseModel):
    rank: int
    run_id: str
    provider: str
    transport_mode: Literal["batch", "streaming"]
    vibe_score: float
    wer_mean: float
    chrf_mean: float | None = None
    ttft_p50_ms: float | None = None
    cost_total_usd: float
    dataset_id: str
    created_at: datetime
