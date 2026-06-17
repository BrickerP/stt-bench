"""Load and validate dataset manifests."""

from __future__ import annotations

import json
from pathlib import Path

from stt_bench.models.dataset import DatasetManifest, SampleRecord
from stt_bench.settings import Settings, get_settings


def _manifest_path(data_dir: Path, dataset_id: str = "default") -> Path:
    # v1: single manifest.json with dataset_id field
    return data_dir / "manifest.json"


def load_manifest(settings: Settings | None = None, dataset_id: str = "default") -> DatasetManifest:
    settings = settings or get_settings()
    path = _manifest_path(settings.data_dir, dataset_id)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path) as f:
        data = json.load(f)

    if data.get("dataset_id") != dataset_id:
        raise ValueError(f"Manifest dataset_id '{data.get('dataset_id')}' != '{dataset_id}'")

    return DatasetManifest(**data)


def resolve_audio_path(sample: SampleRecord, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return (settings.data_dir / sample.audio_path).resolve()


def list_datasets(settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    manifest = load_manifest(settings)
    conditions: dict[str, int] = {}
    for s in manifest.samples:
        conditions[s.condition] = conditions.get(s.condition, 0) + 1
    return [
        {
            "dataset_id": manifest.dataset_id,
            "name": manifest.name,
            "sample_count": len(manifest.samples),
            "conditions": conditions,
        }
    ]


def get_sample(dataset_id: str, sample_id: str, settings: Settings | None = None) -> SampleRecord:
    manifest = load_manifest(settings, dataset_id)
    for s in manifest.samples:
        if s.id == sample_id:
            return s
    raise KeyError(f"Sample '{sample_id}' not found in dataset '{dataset_id}'")


def validate_dataset(settings: Settings | None = None, dataset_id: str = "default") -> dict:
    settings = settings or get_settings()
    manifest = load_manifest(settings, dataset_id)
    errors: list[str] = []
    warnings: list[str] = []

    for sample in manifest.samples:
        path = resolve_audio_path(sample, settings)
        if not path.exists():
            errors.append(f"Missing audio: {sample.id} -> {path}")
        elif path.stat().st_size == 0:
            errors.append(f"Empty audio file: {sample.id}")
        if not sample.reference_text.strip():
            errors.append(f"Empty reference for sample: {sample.id}")

    return {
        "dataset_id": dataset_id,
        "sample_count": len(manifest.samples),
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def get_dataset_stats(settings: Settings | None = None, dataset_id: str = "default") -> dict:
    settings = settings or get_settings()
    manifest = load_manifest(settings, dataset_id)
    conditions: dict[str, int] = {}
    sources: dict[str, int] = {}
    total_duration_est = 0.0

    from stt_bench.providers.base import estimate_audio_duration_s

    for sample in manifest.samples:
        conditions[sample.condition] = conditions.get(sample.condition, 0) + 1
        sources[sample.source] = sources.get(sample.source, 0) + 1
        path = resolve_audio_path(sample, settings)
        if path.exists():
            total_duration_est += estimate_audio_duration_s(path.read_bytes())

    return {
        "dataset_id": dataset_id,
        "name": manifest.name,
        "sample_count": len(manifest.samples),
        "conditions": conditions,
        "sources": sources,
        "estimated_total_duration_s": round(total_duration_est, 2),
    }
