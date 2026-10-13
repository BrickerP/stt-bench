"""Partial revision rate: formula edges and a mock-provider benchmark."""

import asyncio
import time
from pathlib import Path

import pytest

from stt_bench.metrics.compute import compute_sample_metrics
from stt_bench.metrics.revision import compute_partial_revision, group_interim_hypotheses
from stt_bench.models.config import ProviderConfig
from stt_bench.providers.base import StreamPartial
from stt_bench.providers.mock import MockProvider
from stt_bench.report import render_markdown_report
from stt_bench.server.benchmark.runner import BenchmarkRunner
from stt_bench.server.cache import TranscriptionCache
from stt_bench.server.queue import InProcessQueue
from stt_bench.server.results.store import ResultsStore
from stt_bench.server.transcription.service import TranscriptionService
from stt_bench.settings import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples" / "custom-dataset"

# One revision (cat → dog) then two stable updates, including the closing final.
INTERIM_SCRIPT = ["the cat sat", "the dog sat", "the dog sat"]
REFERENCE = "the dog sat"
# Same shape, but the closing final is the custom-dataset reference "a short tone".
BENCHMARK_SCRIPT = ["a long tone", "a short tone", "a short tone"]


def test_not_applicable_without_captured_interims():
    stats = compute_partial_revision(None, final_text="hello world")
    assert stats.partial_revision_rate is None
    assert stats.revised_word_count is None
    assert stats.word_churn is None

    metrics = compute_sample_metrics(
        sample_id="batch",
        reference="hello",
        hypothesis="hello",
        ttft_ms=None,
        total_ms=10,
        audio_duration_s=1.0,
    )
    assert metrics.partial_revision_rate is None
    assert metrics.revised_word_count is None
    assert metrics.word_churn is None


def test_single_partial_and_empty_sequences_are_not_applicable():
    for hypotheses in ([], [[]], [["only one partial"]]):
        stats = compute_partial_revision(hypotheses, final_text="only one partial")
        assert stats.partial_revision_rate is None
        assert stats.revised_word_count is None
        assert stats.word_churn is None


def test_identical_repeats_and_punctuation_are_not_revisions():
    stats = compute_partial_revision(
        [["Hello, World!", "hello world", "HELLO WORLD"]],
        final_text="hello world",
    )
    assert stats.interim_updates == 2
    assert stats.revising_updates == 0
    assert stats.partial_revision_rate == 0.0
    assert stats.revised_word_count == 0
    assert stats.word_churn == 0.0


def test_pure_append_and_contraction_normalization():
    stats = compute_partial_revision(
        [["Don't", "do not go"]],
        final_text="do not go",
    )
    assert stats.partial_revision_rate == 0.0
    assert stats.revised_word_count == 0
    assert stats.word_churn == 0.0


def test_empty_partials():
    stats = compute_partial_revision(
        [["hello world", "", "hello"]],
        final_text="hello",
    )
    assert stats.interim_updates == 2
    assert stats.revising_updates == 1
    assert stats.partial_revision_rate == 0.5
    assert stats.revised_word_count == 2
    assert stats.word_churn == 2.0


def test_leading_empty_partial_is_not_a_revision():
    stats = compute_partial_revision(
        [["", "  ", "hi there"]],
        final_text="hi there",
    )
    assert stats.partial_revision_rate == 0.0
    assert stats.revised_word_count == 0
    assert stats.word_churn == 0.0


def test_word_churn_omitted_when_final_has_no_words():
    stats = compute_partial_revision([["hello", ""]], final_text="")
    assert stats.partial_revision_rate == 1.0
    assert stats.revised_word_count == 1
    assert stats.word_churn is None


def test_middle_insertion_revises_prefix_without_revised_words():
    stats = compute_partial_revision([["a c", "a b c"]], final_text="a b c")
    assert stats.revising_updates == 1
    assert stats.partial_revision_rate == 1.0
    assert stats.revised_word_count == 0
    assert stats.word_churn == 0.0


def test_segments_do_not_cross_finals():
    partials = [
        ("hello", False),
        ("hello world", False),
        ("hello world", True),
        ("good", False),
        ("goodbye", True),
        ("", True),
    ]
    assert group_interim_hypotheses(partials) == [
        ["hello", "hello world", "hello world"],
        ["good", "goodbye"],
    ]
    stats = compute_partial_revision(
        [["one two", "one"], ["three"]],
        final_text="one three",
    )
    assert stats.interim_updates == 1
    assert stats.revising_updates == 1
    assert stats.partial_revision_rate == 1.0
    assert stats.revised_word_count == 1
    assert stats.word_churn == pytest.approx(0.5)


def test_rewrite_rate_matches_script_and_final():
    grouped = group_interim_hypotheses(
        [(text, False) for text in INTERIM_SCRIPT] + [(REFERENCE, True)]
    )
    stats = compute_partial_revision(grouped, final_text=REFERENCE)
    assert stats.interim_updates == 3
    assert stats.revising_updates == 1
    assert stats.partial_revision_rate == pytest.approx(1 / 3)
    assert stats.revised_word_count == 1
    assert stats.word_churn == pytest.approx(1 / 3)


@pytest.fixture
def mock_provider():
    return MockProvider(get_settings())


@pytest.mark.asyncio
async def test_mock_batch_does_not_invent_a_zero_rate(mock_provider):
    config = ProviderConfig(
        provider="mock",
        model="mock-v1",
        transport_mode="batch",
        extra={"reference_text": REFERENCE, "latency_ms": 0},
    )
    result = await mock_provider.transcribe(b"fake audio", config)
    assert result.interim_hypotheses is None
    metrics = compute_sample_metrics(
        sample_id="s",
        reference=REFERENCE,
        hypothesis=result.text,
        ttft_ms=result.timings.ttft_ms,
        total_ms=result.timings.total_ms,
        audio_duration_s=result.audio_duration_s,
        interim_hypotheses=result.interim_hypotheses,
    )
    assert metrics.partial_revision_rate is None


@pytest.mark.asyncio
async def test_mock_monotonic_stream_is_zero_not_null(mock_provider):
    config = ProviderConfig(
        provider="mock",
        model="mock-v1",
        transport_mode="streaming",
        extra={"reference_text": "one two three", "latency_ms": 0},
    )
    result = await mock_provider.transcribe(b"fake", config)
    assert result.interim_hypotheses == [["one", "one two", "one two three"]]
    assert result.confidence is not None
    assert result.confidence.partial_revision_rate == 0.0


@pytest.mark.asyncio
async def test_mock_interim_script_is_deterministic(mock_provider):
    config = ProviderConfig(
        provider="mock",
        model="mock-v1",
        transport_mode="streaming",
        extra={
            "reference_text": REFERENCE,
            "interim_script": INTERIM_SCRIPT,
            "latency_ms": 0,
        },
    )
    first = await mock_provider.transcribe(b"fake", config)
    second = await mock_provider.transcribe(b"fake", config)
    assert first.interim_hypotheses == second.interim_hypotheses
    assert first.interim_hypotheses == [
        ["the cat sat", "the dog sat", "the dog sat", "the dog sat"]
    ]
    assert first.confidence is not None
    assert first.confidence.partial_revision_rate == pytest.approx(1 / 3)
    assert second.confidence is not None
    assert second.confidence.partial_revision_rate == first.confidence.partial_revision_rate


def _revision_run_config(transport_mode: str) -> ProviderConfig:
    extra: dict = {"latency_ms": 0}
    if transport_mode == "streaming":
        extra["interim_script"] = BENCHMARK_SCRIPT
    return ProviderConfig(
        provider="mock",
        model="mock-v1",
        transport_mode=transport_mode,  # type: ignore[arg-type]
        extra=extra,
    )


async def _run_mock(tmp_path: Path, transport_mode: str):
    settings = Settings(
        stt_bench_data_dir=str(EXAMPLE),
        stt_bench_db_path=str(tmp_path / f"{transport_mode}.db"),
        stt_bench_cache_dir=str(tmp_path / f"{transport_mode}-cache"),
    )
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
            transport_mode=transport_mode,
            provider_config=_revision_run_config(transport_mode),
            sample_ids=["tone"],
            force=True,
        )
        deadline = time.monotonic() + 10
        run = created
        while run.status not in ("completed", "failed", "cancelled"):
            if time.monotonic() > deadline:
                raise AssertionError(f"run {created.id} still {run.status}")
            await asyncio.sleep(0.05)
            loaded = await store.get_run(created.id)
            assert loaded is not None
            run = loaded
    finally:
        await queue.stop()
    assert run.status == "completed", run.error
    rows = await store.get_sample_results(run.id)
    return run, rows


@pytest.mark.asyncio
async def test_mock_benchmark_reports_revision_and_batch_is_na(tmp_path):
    streaming, streaming_rows = await _run_mock(tmp_path, "streaming")
    batch, batch_rows = await _run_mock(tmp_path, "batch")

    assert streaming.aggregate_metrics is not None
    assert streaming.aggregate_metrics.partial_revision_rate_mean == pytest.approx(1 / 3)
    assert streaming.aggregate_metrics.word_churn_mean == pytest.approx(1 / 3)
    sample = streaming_rows[0]["metrics"]
    assert sample["partial_revision_rate"] == pytest.approx(1 / 3)
    assert sample["revised_word_count"] == 1
    assert sample["word_churn"] == pytest.approx(1 / 3)
    assert streaming_rows[0]["transcription"]["text"] == "a short tone"
    assert streaming_rows[0]["transcription"]["interim_hypotheses"] == [
        ["a long tone", "a short tone", "a short tone", "a short tone"]
    ]

    assert batch.aggregate_metrics is not None
    assert batch.aggregate_metrics.partial_revision_rate_mean is None
    assert batch.aggregate_metrics.word_churn_mean is None
    assert batch_rows[0]["metrics"]["partial_revision_rate"] is None
    assert batch_rows[0]["transcription"]["interim_hypotheses"] is None

    markdown = render_markdown_report(
        [streaming.model_dump(mode="json"), batch.model_dump(mode="json")]
    )
    assert "Revision" in markdown
    assert "Churn" in markdown
    assert "33.3%" in markdown
    assert "0.33" in markdown
    payload = batch.model_dump(mode="json")
    assert payload["aggregate_metrics"]["partial_revision_rate_mean"] is None
    batch_line = next(line for line in markdown.splitlines() if line.startswith(f"| {batch.id} "))
    assert batch_line.count("—") >= 2


def test_group_interim_hypotheses_keeps_empty_interim():
    grouped = group_interim_hypotheses(
        [
            ("hello world", False),
            ("", False),
            ("hello", False),
            ("hello", True),
        ]
    )
    assert grouped == [["hello world", "", "hello", "hello"]]


def test_stream_partial_shape_matches_grouper():
    """Guard the tuple adapter used by the provider base class."""
    parts = [StreamPartial(text="a b", is_final=False, timestamp_ms=1.0)]
    assert group_interim_hypotheses([(p.text, p.is_final) for p in parts]) == [["a b"]]
