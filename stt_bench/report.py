"""Markdown / JSON benchmark report helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def render_markdown_report(
    runs: list[dict[str, Any]],
    *,
    title: str = "STT Bench Report",
    generated_at: datetime | None = None,
) -> str:
    """Render a PR-pasteable markdown summary for completed benchmark runs."""
    ts = (generated_at or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# {title}",
        "",
        f"_Generated {ts}_",
        "",
        "Provider-neutral evaluation summary (WER / latency / cost / revision / vibe).",
        "",
        "| Run | Provider | Mode | Status | Samples | WER | chrF | Revision | Churn | Vibe | Cost |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if not runs:
        lines.append("| — | — | — | no runs | — | — | — | — | — | — | — |")
    for run in runs:
        cfg = run.get("config") or {}
        agg = run.get("aggregate_metrics") or {}
        wer = agg.get("wer_mean")
        chrf = agg.get("chrf_mean")
        revision = agg.get("partial_revision_rate_mean")
        churn = agg.get("word_churn_mean")
        vibe = run.get("vibe_score")
        cost = agg.get("cost_total_usd")
        revision_cell = f"{revision * 100:.1f}%" if isinstance(revision, (int, float)) else "—"
        churn_cell = f"{churn:.2f}" if isinstance(churn, (int, float)) else "—"
        lines.append(
            "| {id} | {provider} | {mode} | {status} | {samples} | {wer} | {chrf} | "
            "{revision} | {churn} | {vibe} | {cost} |".format(
                id=run.get("id", "—"),
                provider=cfg.get("provider", "—"),
                mode=cfg.get("transport_mode", "—"),
                status=run.get("status", "—"),
                samples=run.get("sample_count", "—"),
                wer=f"{wer * 100:.1f}%" if isinstance(wer, (int, float)) else "—",
                chrf=f"{chrf:.1f}" if isinstance(chrf, (int, float)) else "—",
                revision=revision_cell,
                churn=churn_cell,
                vibe=f"{vibe:.1f}" if isinstance(vibe, (int, float)) else "—",
                cost=f"${cost:.4f}" if isinstance(cost, (int, float)) else "—",
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Mock provider runs are for CI / offline regression only.",
            "- Compare providers on the same dataset and sample set for fair evaluation.",
            (
                "- Revision is the partial revision rate (streaming only). "
                "An em dash means interims were not captured or there was no interim update, "
                "not a rate of zero."
            ),
            (
                "- Churn is revised words divided by normalized final length. "
                "It is omitted when that length is zero."
            ),
            "",
        ]
    )
    return "\n".join(lines)
