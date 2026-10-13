from stt_bench.report import render_markdown_report


def test_render_markdown_report_empty():
    text = render_markdown_report([])
    assert "# STT Bench Report" in text
    assert "no runs" in text


def test_render_markdown_report_with_run():
    text = render_markdown_report(
        [
            {
                "id": "run_abc",
                "status": "completed",
                "sample_count": 2,
                "vibe_score": 71.2,
                "config": {"provider": "mock", "transport_mode": "batch"},
                "aggregate_metrics": {
                    "wer_mean": 0.05,
                    "chrf_mean": 80.0,
                    "cost_total_usd": 0.0,
                },
            }
        ]
    )
    assert "run_abc" in text
    assert "mock" in text
    assert "5.0%" in text
    assert "71.2" in text
    assert "Revision" in text
    # No revision aggregate on this batch-shaped run: not applicable, not zero.
    assert "| 5.0% | 80.0 | — | — | 71.2 | $0.0000 |" in text
