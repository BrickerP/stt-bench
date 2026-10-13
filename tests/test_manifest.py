"""Tests for dataset manifest."""

import json

import pytest

from stt_bench.dataset.loader import load_manifest, validate_dataset
from stt_bench.settings import Settings


def test_manifest_loads():
    manifest = load_manifest(dataset_id="default")
    assert manifest.dataset_id == "default"
    assert len(manifest.samples) == 31


def test_validate_passes():
    result = validate_dataset(dataset_id="default")
    assert result["valid"] is True
    assert result["sample_count"] == 31


def _settings(tmp_path) -> Settings:
    return Settings(stt_bench_data_dir=str(tmp_path))


def test_manifest_must_be_json_object(tmp_path):
    (tmp_path / "manifest.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Manifest must be a JSON object, got list"):
        load_manifest(_settings(tmp_path))


def test_manifest_reads_utf8_reference(tmp_path):
    (tmp_path / "clip.wav").write_bytes(b"RIFF")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_id": "default",
                "name": "utf8",
                "samples": [
                    {
                        "id": "cafe",
                        "audio_path": "clip.wav",
                        "reference_text": "café",
                        "condition": "clean",
                        "source": "synthetic",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = load_manifest(_settings(tmp_path))
    assert manifest.samples[0].reference_text == "café"
