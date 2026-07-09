"""Benchmark run models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from stt_bench.models.config import ProviderConfig


class WERDetails(BaseModel):
    substitutions: int
    deletions: int
    insertions: int
    hits: int


class SampleMetrics(BaseModel):
    sample_id: str
    wer: float
    wer_details: WERDetails
    chrf: float | None = None
    punctuation_f1: float | None = None
    ttft_ms: float | None = None
    total_ms: float
    rtf: float
    cost_usd: float | None = None
    confidence_mean: float | None = None
    hypothesis: str = ""


class AggregateMetrics(BaseModel):
    wer_mean: float
    wer_median: float
    chrf_mean: float | None = None
    punctuation_f1_mean: float | None = None
    ttft_p50_ms: float | None = None
    ttft_p95_ms: float | None = None
    total_ms_p50: float
    total_ms_p95: float
    rtf_mean: float
    cost_total_usd: float
    cost_per_minute_usd: float
    sample_count: int


class BenchmarkRunConfig(BaseModel):
    dataset_id: str
    provider: str
    transport_mode: Literal["batch", "streaming"]
    provider_config: ProviderConfig
    sample_ids: list[str] | None = None
    force: bool = False


class BenchmarkRun(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    config: BenchmarkRunConfig
    created_at: datetime
    completed_at: datetime | None = None
    sample_count: int
    aggregate_metrics: AggregateMetrics | None = None
    vibe_score: float | None = None
    error: str | None = None
