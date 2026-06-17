"""Composite vibe score."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from stt_bench.models.benchmark import AggregateMetrics


class ScoringWeights(BaseModel):
    wer: float = 0.35
    ttft: float = 0.25
    rtf: float = 0.15
    cost: float = 0.15
    confidence: float = 0.10


class VibeScoreBreakdown(BaseModel):
    total: float
    components: dict[str, float]
    weights: ScoringWeights


@lru_cache
def load_scoring_weights(config_dir: str) -> ScoringWeights:
    path = Path(config_dir) / "scoring_weights.yaml"
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return ScoringWeights(**data)
    return ScoringWeights()


def save_scoring_weights(config_dir: str, weights: ScoringWeights) -> None:
    path = Path(config_dir) / "scoring_weights.yaml"
    with open(path, "w") as f:
        yaml.dump(weights.model_dump(), f, default_flow_style=False)
    load_scoring_weights.cache_clear()


def _component_quality(wer_mean: float) -> float:
    return max(0.0, 1.0 - wer_mean)


def _component_ttft(ttft_p50_ms: float | None, is_streaming: bool) -> float | None:
    if not is_streaming:
        return 0.5  # neutral for batch
    if ttft_p50_ms is None:
        return None
    return 1.0 / (1.0 + ttft_p50_ms / 200.0)


def _component_rtf(rtf_mean: float) -> float:
    return 1.0 / (1.0 + rtf_mean)


def _component_cost(cost_per_minute: float) -> float:
    return 1.0 / (1.0 + cost_per_minute / 0.01)


def compute_vibe_score(
    metrics: AggregateMetrics,
    transport_mode: str,
    weights: ScoringWeights | None = None,
    confidence_mean: float | None = None,
    config_dir: str = "./config",
) -> VibeScoreBreakdown:
    w = weights or load_scoring_weights(config_dir)
    is_streaming = transport_mode == "streaming"

    components: dict[str, float | None] = {
        "wer": _component_quality(metrics.wer_mean),
        "ttft": _component_ttft(metrics.ttft_p50_ms, is_streaming),
        "rtf": _component_rtf(metrics.rtf_mean),
        "cost": _component_cost(metrics.cost_per_minute_usd),
        "confidence": confidence_mean if confidence_mean is not None else 0.5,
    }

    # Renormalize weights for unavailable components
    weight_map: dict[str, float] = {
        "wer": w.wer,
        "ttft": w.ttft,
        "rtf": w.rtf,
        "cost": w.cost,
        "confidence": w.confidence,
    }

    active: dict[str, float] = {}
    active_weights: dict[str, float] = {}
    for key, val in components.items():
        if val is not None:
            active[key] = val
            active_weights[key] = weight_map[key]

    total_weight = sum(active_weights.values()) or 1.0
    score = sum(active[k] * (active_weights[k] / total_weight) for k in active) * 100

    return VibeScoreBreakdown(
        total=round(score, 2),
        components={k: round(v, 4) for k, v in active.items()},
        weights=w,
    )
