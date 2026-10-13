"""Sample-level metrics aggregation."""

from stt_bench.metrics.latency import compute_rtf
from stt_bench.metrics.revision import compute_partial_revision
from stt_bench.metrics.wer import compute_chrf, compute_punctuation_f1, compute_wer
from stt_bench.models.benchmark import SampleMetrics, WERDetails


def compute_sample_metrics(
    sample_id: str,
    reference: str,
    hypothesis: str,
    ttft_ms: float | None,
    total_ms: float,
    audio_duration_s: float,
    cost_usd: float | None = None,
    confidence_mean: float | None = None,
    include_chrf: bool = True,
    interim_hypotheses: list[list[str]] | None = None,
) -> SampleMetrics:
    wer, details = compute_wer(reference, hypothesis)
    chrf = compute_chrf(reference, hypothesis) if include_chrf else None
    punct_f1 = compute_punctuation_f1(reference, hypothesis)
    revision = compute_partial_revision(interim_hypotheses, final_text=hypothesis)

    return SampleMetrics(
        sample_id=sample_id,
        wer=wer,
        wer_details=WERDetails(**details),
        chrf=chrf,
        punctuation_f1=punct_f1,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        rtf=compute_rtf(total_ms, audio_duration_s),
        cost_usd=cost_usd,
        confidence_mean=confidence_mean,
        hypothesis=hypothesis,
        partial_revision_rate=revision.partial_revision_rate,
        revised_word_count=revision.revised_word_count,
        word_churn=revision.word_churn,
    )
