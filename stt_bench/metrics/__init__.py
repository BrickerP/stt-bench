"""Metrics computation."""

from stt_bench.metrics.compute import compute_sample_metrics
from stt_bench.metrics.cost import estimate_provider_cost, load_pricing
from stt_bench.metrics.latency import aggregate_latencies, compute_rtf
from stt_bench.metrics.wer import (
    compute_chrf,
    compute_punctuation_f1,
    compute_wer,
    normalize_text,
)

__all__ = [
    "aggregate_latencies",
    "compute_chrf",
    "compute_punctuation_f1",
    "compute_provider_cost",
    "compute_rtf",
    "compute_sample_metrics",
    "compute_wer",
    "load_pricing",
    "normalize_text",
]

# alias
compute_provider_cost = estimate_provider_cost
