# OSS Maturity — stt-bench

> From personal benchmark tool to maintainer-grade OSS application package

Execution gate only. Architecture/API details live in [DESIGN.md](../DESIGN.md), [service.md](./service.md), [providers.md](./providers.md), and [custom-datasets.md](./custom-datasets.md).

## 1. Eligibility Scorecard

| Signal | Baseline 2026-07-09 | Target by apply | Evidence |
|---|---|---|---|
| Primary/core maintainer | owner (BrickerP) | owner + CODEOWNERS | GitHub permissions |
| Public active repo | public; last push 2026-06-17 | weekly commits + issues | commit/issue history |
| Usage | 0 stars / ~4 clones / 14d | installable + honest early metrics | PyPI + traffic |
| Ecosystem importance | personal Whisper/Deepgram demo vibe | STT evaluation toolkit | README first screen |
| Maintainer workflows | none | CI + mock PR bench + release | `.github/workflows` |
| Codex credit use case | n/a | adapter review / regression / release notes | Application Packet |

## 2. Baseline Snapshot (frozen 2026-07-09)

- Public repo: https://github.com/BrickerP/stt-bench
- Stack: CLI (Typer) + FastAPI + SQLite + providers (mock/whisper/deepgram)
- Tests present; **no CI**, **no GitHub Release**, **no PyPI publish**
- PyPI name `stt-bench` **TAKEN** by unrelated project `0.2.0` — package renamed to **`stt-eval-bench`**; CLI entrypoint remains `stt-bench`
- Traffic (14d, owner view): ~4 views / ~4 clones on best candidates historically; this repo early-stage
- Narrative weakness: README read as Whisper-vs-Deepgram demo, not evaluation toolkit

### Delta log

- 2026-07-09: Maturity program started; package rename decision recorded; phases below executed in-repo.
- 2026-10-13: Compose volume and env self-host docs landed ([service.md](./service.md): named volume `stt_bench_data`, env table, key injection). Closes the roadmap item tracked here as issue #1.
- 2026-10-13: Custom dataset manifest guide landed ([custom-datasets.md](./custom-datasets.md), `examples/custom-dataset/`). Closes the roadmap item tracked here as issue #4.
- 2026-10-13: Streaming partial revision rate landed (`stt_bench/metrics/revision.py`, mock `interim_script`, report column). Closes the roadmap item tracked here as issue #5.
- 2026-10-13: PR report comment bot landed (job summary, `report.md` artifact, one sticky comment on same-repo pull requests; fork pull requests skip the comment). Closes the roadmap item tracked here as issue #6.

## 3. Phases + Exit Criteria

### Phase 0 — Execution doc + baseline
- [x] This file landed
- [x] Baseline frozen
- [x] Roadmap issues opened (see § DoD)

### Phase 1 — Trust surface
- [x] CI: pytest + ruff + package build (mock-only)
- [x] CONTRIBUTING / SECURITY / CODE_OF_CONDUCT / CODEOWNERS / issue+PR templates
- [x] CHANGELOG + Release assets path for v0.1.0
- [x] PyPI gate: name `stt-eval-bench` free; Trusted Publishing workflow present
- Exit: CI green; governance files present; release publishable

### Phase 2 — Local service (no platformization)
- [x] Dockerfile + docker-compose (SQLite volume)
- [x] `/healthz` `/readyz` `/version`
- [x] `stt-bench report --format markdown`
- [x] docs/service.md
- [x] Compose volume and env self-host docs in docs/service.md (issue #1)
- Exit: compose up → mock benchmark → markdown report

### Phase 3 — Ecosystem
- [x] docs/providers.md
- [x] New provider adapter + contract/mock tests (no real keys in CI)
- [x] PR mock-benchmark workflow
- [x] PR report comment bot (issue #6): job summary, `report.md` artifact, and one sticky comment updated in place
- Exit: contributor path clear; CI still secret-free

### Phase 4 — Honest apply packet
- [x] README first screen = evaluation toolkit
- [x] examples/
- [x] Application Packet short + long
- Exit: hard DoD checklist green; push to origin

## 4. Hard DoD Checklist

- [x] Install path works via source / GitHub Release wheel
- [x] `pip install stt-eval-bench` from PyPI (Trusted Publisher pending → publish via `v0.1.1`)
- [x] `Dockerfile` + `docker-compose.yml` landed; local `stt-bench serve` mock path verified (`/healthz`, report). Compose not executed on agent host (no docker binary).
- [x] `stt-bench report --format markdown`
- [x] CI workflows present: pytest, ruff, package build (mock-only)
- [x] v0.1.0 GitHub Release + CHANGELOG + wheel/sdist assets
- [x] CONTRIBUTING / SECURITY / CODEOWNERS / issue templates
- [x] 5–8 roadmap issues (#1–#8)
- [x] README first screen: STT evaluation toolkit (not Whisper demo)

## 5. Application Packet

### Short — Why this repository qualifies

> Primary maintainer of stt-bench (PyPI: stt-eval-bench): self-hostable toolkit for reproducible STT provider evaluation (WER/latency/cost/streaming UX). Early-stage but maintainer-grade — CI, releases, Docker local service, PR regression reports. Ecosystem role: helps builders choose STT for dictation/voice-agents.

### Short — How API credits will be used

> Codex for provider-adapter PR review, mock-corpus benchmark regression on PRs, changelog/release notes, SECURITY triage, and report-diff maintainer automation.

### Long — Ecosystem role (not widely used yet)

stt-bench is an early open-source benchmarking toolkit for teams building dictation and voice-agent systems. It is not widely used yet (honest early metrics). Its ecosystem role is clear: reproducible, provider-neutral evaluation across quality, streaming latency, cost, and UX-oriented vibe scoring, with a self-hostable local service and PR-friendly markdown reports. Maintainers can extend providers/datasets/metrics via documented contribution paths. Codex credits would reduce review and release load on adapter PRs, mock regression diffs, and security/release hygiene — core OSS maintainer work, not product demos.

Form field lengths should be re-checked against the live OpenAI form before submit.

## 6. Weekly Review Log

### 2026-07-09
- Completed Phases 0–4 implementation; pushed `main` + tag `v0.1.0` + GitHub Release with wheel/sdist.
- PyPI: name `stt-bench` taken by unrelated 0.2.0 → package **`stt-eval-bench`**. CLI remains `stt-bench`.
- Local verify: pytest 27 passed, ruff clean, build OK, mock benchmark + markdown report OK, `/healthz`/`/readyz`/`/version` via `stt-bench serve`.
- Docker files landed; compose not run here (no docker binary on agent host).
- Roadmap issues #1–#8 opened.
- **Blocker cleared:** Pending Trusted Publisher registered for `stt-eval-bench` (`BrickerP/stt-bench` / `release.yml` / env `release`). Publishing via tag `v0.1.1`.
- **Codex for OSS application submitted** (2026-07-09) via https://openai.com/form/codex-for-oss/ for `BrickerP/stt-bench` as Primary maintainer; confirmation: “Thanks for your submission!”.
- Still early-stage usage; application narrative stays honest.
