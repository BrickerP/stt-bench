"""Tests for dataset manifest."""

from stt_bench.dataset.loader import load_manifest, validate_dataset


def test_manifest_loads():
    manifest = load_manifest(dataset_id="default")
    assert manifest.dataset_id == "default"
    assert len(manifest.samples) == 31


def test_validate_passes():
    result = validate_dataset(dataset_id="default")
    assert result["valid"] is True
    assert result["sample_count"] == 31
