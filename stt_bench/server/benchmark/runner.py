"""Benchmark runner orchestration."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from stt_bench.dataset.registry import DatasetRegistry
from stt_bench.metrics.compute import compute_sample_metrics
from stt_bench.metrics.latency import aggregate_latencies
from stt_bench.models.benchmark import (
    AggregateMetrics,
    BenchmarkRun,
    BenchmarkRunConfig,
    SampleMetrics,
)
from stt_bench.models.config import ProviderConfig
from stt_bench.scoring.vibe import compute_vibe_score
from stt_bench.server.queue import BenchmarkJob, InProcessQueue, ProgressEvent
from stt_bench.server.results.store import ResultsStore
from stt_bench.server.transcription.service import TranscriptionService
from stt_bench.settings import Settings


def _naive_utc_now() -> datetime:
    """UTC clock time with no tzinfo, same value shape as datetime.utcnow()."""
    return datetime.now(UTC).replace(tzinfo=None)


class BenchmarkRunner:
    def __init__(
        self,
        settings: Settings,
        store: ResultsStore,
        transcription: TranscriptionService,
        queue: InProcessQueue,
    ):
        self.settings = settings
        self.store = store
        self.transcription = transcription
        self.queue = queue
        self.registry = DatasetRegistry(settings)
        queue.set_handler(self._handle_job)

    async def create_run(
        self,
        dataset_id: str,
        provider: str,
        transport_mode: str,
        provider_config: ProviderConfig,
        sample_ids: list[str] | None = None,
        force: bool = False,
    ) -> BenchmarkRun:
        try:
            manifest = self.registry.load(dataset_id)
        except (FileNotFoundError, ValueError) as e:
            raise ValueError(f"DATASET_NOT_FOUND: {e}") from e

        samples = manifest.samples
        if sample_ids:
            id_set = set(sample_ids)
            samples = [s for s in samples if s.id in id_set]

        run_id = f"run_{_naive_utc_now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        config = BenchmarkRunConfig(
            dataset_id=dataset_id,
            provider=provider,
            transport_mode=transport_mode,
            provider_config=provider_config,
            sample_ids=sample_ids,
            force=force,
        )
        run = BenchmarkRun(
            id=run_id,
            status="queued",
            config=config,
            created_at=_naive_utc_now(),
            sample_count=len(samples),
        )
        await self.store.save_run(run)

        job = BenchmarkJob(
            run_id=run_id,
            dataset_id=dataset_id,
            provider=provider,
            transport_mode=transport_mode,
            config=provider_config,
            sample_ids=sample_ids,
            force=force,
        )
        await self.queue.enqueue(job)
        return run

    async def _handle_job(self, job: BenchmarkJob) -> None:
        run = await self.store.get_run(job.run_id)
        if not run:
            return

        run.status = "running"
        await self.store.save_run(run)
        await self.queue.emit(
            ProgressEvent(run_id=job.run_id, event_type="started", message="Benchmark started")
        )

        try:
            manifest = self.registry.load(job.dataset_id)
            samples = manifest.samples
            if job.sample_ids:
                id_set = set(job.sample_ids)
                samples = [s for s in samples if s.id in id_set]

            sem = asyncio.Semaphore(self.settings.stt_bench_max_concurrent_samples)
            sample_metrics: list[SampleMetrics] = []
            total_audio_s = 0.0
            done = 0

            async def process_sample(sample):
                nonlocal done, total_audio_s
                async with sem:
                    path = self.registry.resolve_path(sample)
                    result = await self.transcription.transcribe_path(
                        path,
                        job.provider,
                        job.config,
                        force=job.force,
                        reference_text=sample.reference_text,
                    )
                    sm = compute_sample_metrics(
                        sample_id=sample.id,
                        reference=sample.reference_text,
                        hypothesis=result.text,
                        ttft_ms=result.timings.ttft_ms,
                        total_ms=result.timings.total_ms,
                        audio_duration_s=result.audio_duration_s,
                        cost_usd=result.cost_usd,
                        confidence_mean=result.confidence.mean if result.confidence else None,
                    )
                    await self.store.save_sample_result(job.run_id, sample.id, sm, result)
                    sample_metrics.append(sm)
                    total_audio_s += result.audio_duration_s
                    done += 1
                    await self.queue.emit(
                        ProgressEvent(
                            run_id=job.run_id,
                            event_type="sample_done",
                            sample_id=sample.id,
                            progress=done / len(samples),
                            message=f"Completed {sample.id}",
                        )
                    )

            await asyncio.gather(*[process_sample(s) for s in samples])

            agg_dict = aggregate_latencies(
                ttft_values=[m.ttft_ms for m in sample_metrics],
                total_values=[m.total_ms for m in sample_metrics],
                rtf_values=[m.rtf for m in sample_metrics],
                wer_values=[m.wer for m in sample_metrics],
                cost_values=[m.cost_usd or 0.0 for m in sample_metrics],
                total_audio_duration_s=total_audio_s,
                chrf_values=[m.chrf for m in sample_metrics],
                punctuation_f1_values=[m.punctuation_f1 for m in sample_metrics],
            )
            agg = AggregateMetrics(**agg_dict)

            confidences = [m.confidence_mean for m in sample_metrics if m.confidence_mean is not None]
            conf_mean = sum(confidences) / len(confidences) if confidences else None

            vibe = compute_vibe_score(
                agg,
                job.transport_mode,
                confidence_mean=conf_mean,
                config_dir=str(self.settings.config_dir),
            )

            run.status = "completed"
            run.completed_at = _naive_utc_now()
            run.aggregate_metrics = agg
            run.vibe_score = vibe.total
            await self.store.save_run(run)

            await self.queue.emit(
                ProgressEvent(
                    run_id=job.run_id,
                    event_type="completed",
                    progress=1.0,
                    message="Benchmark completed",
                    data={"vibe_score": vibe.total, "wer_mean": agg.wer_mean},
                )
            )
        except Exception as e:  # noqa: BLE001 — record the failed run and keep the worker alive
            run.status = "failed"
            run.completed_at = _naive_utc_now()
            run.error = str(e)
            await self.store.save_run(run)
            await self.queue.emit(
                ProgressEvent(
                    run_id=job.run_id,
                    event_type="failed",
                    message=str(e),
                )
            )
