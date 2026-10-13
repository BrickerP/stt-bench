"""Sticky pull-request comment for the mock benchmark report.

The workflow in ``.github/workflows/benchmark.yml`` calls this module to
build one comment body and decide whether posting it is safe. The comment is
found on later pushes by ``MARKER``. Fork pull requests are not commented on:
``pull_request`` from a fork checks out untrusted code and GitHub makes
``GITHUB_TOKEN`` read-only. The job summary and artifact still publish.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MARKER = "<!-- stt-bench-mock-report -->"
ARTIFACT_NAME = "stt-bench-report"
# GitHub rejects issue and pull request comment bodies above 65,536 characters.
MAX_COMMENT_CHARS = 65_000


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def _opted_out(repo_variable: str) -> bool:
    return repo_variable.strip().lower() == "false"


def should_post_comment(
    *,
    event_name: str,
    repo_variable: str = "",
    head_repo: str = "",
    repository: str = "",
    dispatch_post: str = "false",
    pr_number: str = "",
) -> tuple[bool, str]:
    """Return whether to upsert the sticky comment, and a one-line reason."""
    if _opted_out(repo_variable):
        return False, "STT_BENCH_PR_COMMENT=false; skipping the sticky comment"
    if event_name == "pull_request":
        if head_repo and repository and head_repo == repository:
            return True, "same-repository pull request"
        return (
            False,
            (
                "pull request head is not in this repository; skipping the sticky comment "
                "(fork tokens are read-only). The report is in the job summary and the "
                f"{ARTIFACT_NAME} artifact"
            ),
        )
    if event_name == "workflow_dispatch":
        if not _truthy(dispatch_post):
            return False, "workflow_dispatch post_pr_comment is false; skipping the sticky comment"
        if not pr_number.strip():
            return False, "workflow_dispatch has no pull request number; skipping the sticky comment"
        return True, f"workflow_dispatch targeting pull request {pr_number.strip()}"
    return False, f"event {event_name} has no pull request; skipping the sticky comment"


def _clip(text: str, budget: int) -> str:
    if budget <= 0 or not text:
        return ""
    if len(text) <= budget:
        return text
    clipped = text[:budget]
    newline = clipped.rfind("\n")
    if newline >= 0:
        clipped = clipped[:newline]
    return clipped.rstrip()


def _header(sha: str, artifact_name: str, run_url: str) -> str:
    pointer = f" ([workflow run]({run_url}))" if run_url else ""
    return (
        f"{MARKER}\n"
        "## STT Bench mock report\n"
        "\n"
        f"Mock benchmark for `{sha}`. The full report is in the job summary and the "
        f"`{artifact_name}` artifact{pointer}.\n"
        "\n"
    )


def _truncation_note(artifact_name: str) -> str:
    return (
        "\n\n---\n\n"
        "> Report truncated to fit GitHub's pull request comment size limit. "
        f"Download the `{artifact_name}` artifact from the workflow run for the full markdown.\n"
    )


def build_comment(
    report: str,
    *,
    sha: str,
    artifact_name: str = ARTIFACT_NAME,
    run_url: str = "",
    limit: int = MAX_COMMENT_CHARS,
) -> str:
    """Build the sticky comment body, truncating the report below ``limit``."""
    header = _header(sha, artifact_name, run_url)
    note = _truncation_note(artifact_name)
    if limit < len(header) + len(note):
        raise ValueError(f"comment limit {limit} is smaller than the header and truncation note")
    full = f"{header}{report.strip()}\n"
    if len(full) <= limit:
        return full
    clipped = _clip(report.strip(), limit - len(header) - len(note))
    return f"{header}{clipped}{note}"


def _write_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"{key} must be a single line")
            handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the sticky mock-benchmark PR comment.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--artifact", default=ARTIFACT_NAME)
    parser.add_argument("--event-name", default="pull_request")
    parser.add_argument("--repo-variable", default="")
    parser.add_argument("--head-repo", default="")
    parser.add_argument("--repository", default="")
    parser.add_argument("--dispatch-post", default="false")
    parser.add_argument("--pr-number", default="")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)

    report = args.report.read_text(encoding="utf-8")
    post, reason = should_post_comment(
        event_name=args.event_name,
        repo_variable=args.repo_variable,
        head_repo=args.head_repo,
        repository=args.repository,
        dispatch_post=args.dispatch_post,
        pr_number=args.pr_number,
    )
    body = build_comment(
        report,
        sha=args.sha,
        artifact_name=args.artifact,
        run_url=args.run_url,
    )
    payload = {"marker": MARKER, "body": body}
    args.out.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.github_output is not None:
        _write_github_output(
            args.github_output,
            {
                "post": "true" if post else "false",
                "reason": reason,
                "pr_number": args.pr_number.strip(),
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
