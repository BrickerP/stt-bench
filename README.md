# STT Bench

[![CI](https://github.com/BrickerP/stt-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/BrickerP/stt-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Self-hostable STT evaluation toolkit** for comparing speech-to-text providers on quality (WER/chrF), streaming latency, cost, and a dictation-oriented vibe score.

This is **not** a Whisper demo. It is a reproducible harness for builders choosing STT for dictation and voice-agent systems — CLI + local Docker service + PR-friendly reports.

PyPI package name: **`stt-eval-bench`** (the name `stt-bench` was already taken on PyPI). CLI command remains **`stt-bench`**.

## Quick start (2 minutes)

```bash
pip install stt-eval-bench

stt-bench benchmark run --provider mock --force
stt-bench report --format markdown
stt-bench results leaderboard
```

No API keys required for mock runs.

From source / editable install:

```bash
git clone https://github.com/BrickerP/stt-bench.git
cd stt-bench
pip install -e ".[dev]"
```

## What you get

| Surface | Description |
|---|---|
| **CLI** | `compare`, `listen`, `benchmark`, `report`, `results` |
| **Local service** | `stt-bench serve` or `docker compose up` — FastAPI + SQLite |
| **Providers** | `mock`, `whisper`, `deepgram`, `assemblyai` (pluggable) |
| **Reports** | Markdown suitable for PR comments |

## Self-host in 60s

```bash
docker compose up --build -d
curl -s http://127.0.0.1:8766/healthz
curl -s http://127.0.0.1:8766/version
```

Details: [docs/service.md](docs/service.md)

## With real providers

```bash
cp .env.example .env   # OPENAI_API_KEY / DEEPGRAM_API_KEY / ASSEMBLYAI_API_KEY
stt-bench listen 1089-134686-0000_noisy
stt-bench compare --all
```

## Dataset

31 samples in `data/manifest.json` (LibriSpeech subset + one noisy clip).

```bash
stt-bench samples
stt-bench dataset validate
```

Your own audio and reference transcripts: [docs/custom-datasets.md](docs/custom-datasets.md). The example under `examples/custom-dataset/` runs with `--provider mock` and no API key.

## Metrics

WER · chrF · punctuation F1 · partial revision rate (streaming) · TTFT · RTF · cost · vibe score — see `stt-bench math`.

## CI

Pull requests to `main` run tests (`.github/workflows/ci.yml`) and a mock benchmark (`.github/workflows/benchmark.yml`). No API keys are used.

The mock benchmark writes `report.md` to the job summary and uploads it as the `stt-bench-report` artifact. On a pull request from this repository it also posts or updates one comment, found by the hidden marker `<!-- stt-bench-mock-report -->`. Later pushes update that comment. Fork pull requests skip the comment, because the workflow token is read-only there; the summary and artifact are still published. A read-only token on any pull request (for example Dependabot) is skipped the same way and does not fail the job.

Set the repository variable `STT_BENCH_PR_COMMENT` to `false` to stop comments. A manual run can set `post_pr_comment` to false, or pass `pr_number` to update the comment on that pull request.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/providers.md](docs/providers.md).  
Maturity / Codex-for-OSS execution gate: [docs/OSS_MATURITY.md](docs/OSS_MATURITY.md).  
Architecture: [DESIGN.md](DESIGN.md).

## License

MIT — see [LICENSE](./LICENSE). LibriSpeech data: [CC BY 4.0](https://www.openslr.org/12/).
