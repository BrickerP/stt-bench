"""Cost estimation from pricing config."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from stt_bench.settings import Settings


@lru_cache
def load_pricing(config_dir: str) -> dict:
    path = Path(config_dir) / "pricing.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def estimate_provider_cost(
    provider: str,
    model: str,
    audio_duration_s: float,
    settings: Settings,
) -> float:
    pricing = load_pricing(str(settings.config_dir))
    provider_rates = pricing.get(provider, {})
    rate = provider_rates.get(model) or provider_rates.get("default", 0.0)
    return (audio_duration_s / 60.0) * float(rate)
