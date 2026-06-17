"""Latency metrics."""

import statistics
from typing import Sequence


def compute_rtf(total_ms: float, audio_duration_s: float) -> float:
    if audio_duration_s <= 0:
        return 0.0
    return total_ms / (audio_duration_s * 1000)


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * pct / 100
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def aggregate_latencies(
    ttft_values: list[float | None],
    total_values: list[float],
    rtf_values: list[float],
    wer_values: list[float],
    cost_values: list[float],
    total_audio_duration_s: float,
    chrf_values: list[float | None] | None = None,
    punctuation_f1_values: list[float | None] | None = None,
) -> dict:
    ttft_clean = [v for v in ttft_values if v is not None]
    chrf_clean = [v for v in (chrf_values or []) if v is not None]
    punct_clean = [v for v in (punctuation_f1_values or []) if v is not None]
    return {
        "wer_mean": statistics.mean(wer_values) if wer_values else 0.0,
        "wer_median": statistics.median(wer_values) if wer_values else 0.0,
        "chrf_mean": statistics.mean(chrf_clean) if chrf_clean else None,
        "punctuation_f1_mean": statistics.mean(punct_clean) if punct_clean else None,
        "ttft_p50_ms": _percentile(ttft_clean, 50) if ttft_clean else None,
        "ttft_p95_ms": _percentile(ttft_clean, 95) if ttft_clean else None,
        "total_ms_p50": _percentile(total_values, 50) if total_values else 0.0,
        "total_ms_p95": _percentile(total_values, 95) if total_values else 0.0,
        "rtf_mean": statistics.mean(rtf_values) if rtf_values else 0.0,
        "cost_total_usd": sum(cost_values),
        "cost_per_minute_usd": (
            (sum(cost_values) / (total_audio_duration_s / 60)) if total_audio_duration_s > 0 else 0.0
        ),
        "sample_count": len(wer_values),
    }
