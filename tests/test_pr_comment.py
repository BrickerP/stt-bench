import json
from pathlib import Path

from stt_bench.pr_comment import (
    ARTIFACT_NAME,
    MARKER,
    build_comment,
    main,
    should_post_comment,
)


def test_short_report_keeps_body_and_marker():
    body = build_comment("# Report\n\nok\n", sha="abc123", run_url="https://example.test/run/1")
    assert body.startswith(MARKER)
    assert "# Report" in body
    assert "ok" in body
    assert "abc123" in body
    assert "https://example.test/run/1" in body
    assert ARTIFACT_NAME in body
    assert "truncated" not in body.lower()


def test_long_report_stays_under_limit_and_points_at_artifact():
    report = "\n".join(f"row {index} " + ("x" * 40) for index in range(400))
    limit = 1_500
    body = build_comment(report, sha="deadbeef", artifact_name="stt-bench-report", limit=limit)
    assert len(body) <= limit
    assert body.startswith(MARKER)
    assert "truncated" in body.lower()
    assert "`stt-bench-report`" in body
    assert "row 399" not in body
    assert report not in body


def test_comment_limit_too_small_raises():
    try:
        build_comment("hello", sha="abc", limit=10)
    except ValueError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_same_repo_pull_request_posts():
    post, reason = should_post_comment(
        event_name="pull_request",
        head_repo="BrickerP/stt-bench",
        repository="BrickerP/stt-bench",
    )
    assert post is True
    assert "same-repository" in reason


def test_fork_pull_request_skips():
    post, reason = should_post_comment(
        event_name="pull_request",
        head_repo="other/stt-bench",
        repository="BrickerP/stt-bench",
    )
    assert post is False
    assert "fork" in reason


def test_repo_variable_opts_out():
    post, _reason = should_post_comment(
        event_name="pull_request",
        repo_variable="False",
        head_repo="BrickerP/stt-bench",
        repository="BrickerP/stt-bench",
    )
    assert post is False


def test_workflow_dispatch_requires_opt_in_and_pr_number():
    skipped, _reason = should_post_comment(
        event_name="workflow_dispatch",
        dispatch_post="false",
        pr_number="12",
    )
    assert skipped is False
    missing, _reason = should_post_comment(
        event_name="workflow_dispatch",
        dispatch_post="true",
        pr_number="  ",
    )
    assert missing is False
    post, reason = should_post_comment(
        event_name="workflow_dispatch",
        dispatch_post="true",
        pr_number=" 12 ",
    )
    assert post is True
    assert "12" in reason


def test_cli_writes_payload_and_skips_fork(tmp_path: Path):
    report = tmp_path / "report.md"
    report.write_text("# hi\n", encoding="utf-8")
    out = tmp_path / "payload.json"
    github_output = tmp_path / "github_output.txt"
    code = main(
        [
            "--report",
            str(report),
            "--sha",
            "abc123",
            "--out",
            str(out),
            "--event-name",
            "pull_request",
            "--head-repo",
            "other/stt-bench",
            "--repository",
            "BrickerP/stt-bench",
            "--github-output",
            str(github_output),
        ]
    )
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["marker"] == MARKER
    assert payload["marker"] in payload["body"]
    assert "# hi" in payload["body"]
    text = github_output.read_text(encoding="utf-8")
    assert "post=false\n" in text
    assert "pr_number=\n" in text
