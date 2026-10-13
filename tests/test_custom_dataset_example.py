"""The documented custom-dataset example stays runnable with the mock provider."""

import asyncio
import time
from pathlib import Path

from stt_bench.dataset.loader import load_manifest, resolve_audio_path, validate_dataset
from stt_bench.models.config import ProviderConfig
from stt_bench.server.benchmark.runner import BenchmarkRunner
from stt_bench.server.cache import TranscriptionCache
from stt_bench.server.queue import InProcessQueue
from stt_bench.server.results.store import ResultsStore
from stt_bench.server.transcription.service import TranscriptionService
from stt_bench.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples" / "custom-dataset"


def test_relative_data_dir_ignores_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings(stt_bench_data_dir="examples/custom-dataset")
    assert settings.data_dir == EXAMPLE
    manifest = load_manifest(settings, dataset_id="default")
    tone = next(sample for sample in manifest.samples if sample.id == "tone")
    resolved = resolve_audio_path(tone, settings)
    assert resolved == (EXAMPLE / "clips" / "tone.wav").resolve()
    assert resolved.is_file()


async def test_example_manifest_mock_benchmark(tmp_path):
    settings = Settings(
        stt_bench_data_dir=str(EXAMPLE),
        stt_bench_db_path=str(tmp_path / "results.db"),
        stt_bench_cache_dir=str(tmp_path / "cache"),
    )
    manifest = load_manifest(settings, dataset_id="default")
    assert [sample.id for sample in manifest.samples] == ["tone", "silence"]
    report = validate_dataset(settings, dataset_id="default")
    assert report["valid"] is True
    assert report["sample_count"] == 2
    assert report["warnings"] == []

    store = ResultsStore(settings.db_path)
    await store.init()
    queue = InProcessQueue()
    transcription = TranscriptionService(settings, TranscriptionCache(store))
    runner = BenchmarkRunner(settings, store, transcription, queue)
    await queue.start()
    try:
        created = await runner.create_run(
            dataset_id="default",
            provider="mock",
            transport_mode="batch",
            provider_config=ProviderConfig(
                provider="mock",
                model="mock-v1",
                transport_mode="batch",
            ),
            force=True,
        )
        deadline = time.monotonic() + 10
        run = created
        while run.status not in ("completed", "failed", "cancelled"):
            if time.monotonic() > deadline:
                raise AssertionError(f"run {created.id} still {run.status}")
            await asyncio.sleep(0.05)
            run = await store.get_run(created.id)
    finally:
        await queue.stop()

    assert run.status == "completed", run.error
    assert run.sample_count == 2
    assert run.aggregate_metrics is not None
    assert run.aggregate_metrics.wer_mean == 0.0

    rows = {row["sample_id"]: row for row in await store.get_sample_results(run.id)}
    assert rows["tone"]["transcription"]["text"] == "a short tone"
    assert rows["silence"]["transcription"]["text"] == "a short silence"
