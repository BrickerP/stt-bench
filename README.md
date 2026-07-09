# STT Bench

[![CI](https://github.com/BrickerP/stt-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/BrickerP/stt-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Self-hostable STT evaluation toolkit** for comparing speech-to-text providers on quality (WER/chrF), streaming latency, cost, and a dictation-oriented vibe score.

This is **not** a Whisper demo. It is a reproducible harness for builders choosing STT for dictation and voice-agent systems — CLI + local Docker service + PR-friendly reports.

PyPI package name: **`stt-eval-bench`** (the name `stt-bench` was already taken on PyPI). CLI command remains **`stt-bench`**.

## Quick start (2 minutes)

```bash
# From source (recommended until PyPI Trusted Publishing is configured):
git clone https://github.com/BrickerP/stt-bench.git
cd stt-bench
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Or install the GitHub Release wheel:
# pip install https://github.com/BrickerP/stt-bench/releases/download/v0.1.0/stt_eval_bench-0.1.0-py3-none-any.whl

stt-bench benchmark run --provider mock --force
stt-bench report --format markdown
stt-bench results leaderboard
```

No API keys required for mock runs.

PyPI name **`stt-eval-bench`** is reserved for Trusted Publishing (`release.yml` + pypi.org publisher). Until that is configured once on PyPI, use source or the Release wheel above — do not assume `pip install stt-eval-bench` works yet.

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

## Metrics

WER · chrF · punctuation F1 · TTFT · RTF · cost · vibe score — see `stt-bench math`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/providers.md](docs/providers.md).  
Maturity / Codex-for-OSS execution gate: [docs/OSS_MATURITY.md](docs/OSS_MATURITY.md).  
Architecture: [DESIGN.md](DESIGN.md).

## License

MIT — see [LICENSE](./LICENSE). LibriSpeech data: [CC BY 4.0](https://www.openslr.org/12/).
