# STT Bench

Compare **OpenAI Whisper** (batch) vs **Deepgram** (streaming) for dictation-style speech-to-text — with WER, chrF, latency, cost, and a composite **vibe score**.

Built for engineers evaluating which STT provider feels best for real-time dictation.

## Quick start (2 minutes)

```bash
git clone https://github.com/BrickerP/stt-bench.git
cd stt-bench
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # add OPENAI_API_KEY + DEEPGRAM_API_KEY
```

**No API keys?** Use mock for offline benchmarks:

```bash
stt-bench benchmark run --provider mock --force
stt-bench results leaderboard
```

**With API keys — the demo command:**

```bash
stt-bench listen 1089-134686-0000_noisy
```

Plays the audio, runs Whisper + Deepgram in parallel, prints side-by-side metrics and transcripts.

## What you get

| Feature | Description |
|---------|-------------|
| **compare** | Head-to-head Whisper vs Deepgram on one clip |
| **listen** | Play audio + compare while you listen |
| **benchmark** | Batch eval over 31-clip LibriSpeech subset |
| **leaderboard** | Rank runs by vibe score |
| **math** | Show all metric formulas (`stt-bench math`) |

## Dataset (included)

31 samples in `data/manifest.json`:

- **30 clean** — LibriSpeech test-clean (`data/librispeech/`)
- **1 noisy** — pink-noise overlay (`data/noisy/1089-134686-0000_noisy.flac`)

```bash
stt-bench samples              # list all
stt-bench dataset validate     # verify audio + ground truth
```

Example sample ID: **`1089-134686-0000_noisy`**

## Common commands

```bash
# Side-by-side on noisy clip (default)
stt-bench compare

# Clean vs noisy same sentence
stt-bench compare 1089-134686-0000
stt-bench compare 1089-134686-0000_noisy

# Live streaming partials (Deepgram)
stt-bench transcribe file data/noisy/1089-134686-0000_noisy.flac \
  --provider deepgram --stream --force

# Full corpus benchmark
stt-bench compare --all

# Results
stt-bench results leaderboard --exclude-mock
stt-bench results show RUN_ID

# Metric formulas
stt-bench math
stt-bench compare --math
```

## API keys

Edit `.env` after copying from `.env.example`:

```env
OPENAI_API_KEY=sk-proj-...
DEEPGRAM_API_KEY=...
```

Never commit `.env`. Use `--provider mock` for offline testing.

## Optional: HTTP server

```bash
stt-bench serve --port 8766
stt-bench --api-url http://127.0.0.1:8766 results leaderboard
```

Default port is **8766** (8765 often taken by Cursor MCP proxy on macOS).

## Metrics

| Metric | What it measures |
|--------|------------------|
| **WER** | Word accuracy (normalized) |
| **chrF** | Character-level match (punctuation/casing) |
| **TTFT** | Time to first token (streaming only) |
| **RTF** | Processing speed vs audio length |
| **Vibe** | Weighted composite for dictation UX (0–100) |

See `stt-bench math` for formulas. Weights in `config/scoring_weights.yaml`.

## Architecture

- **CLI** — Typer + Rich (local by default, optional REST client)
- **Providers** — pluggable adapters (`mock`, `whisper`, `deepgram`)
- **Storage** — SQLite for runs + cache
- **Design doc** — [DESIGN.md](./DESIGN.md)

## Development

```bash
pytest -q
ruff check stt_bench tests
```

## License

MIT — see [LICENSE](./LICENSE). LibriSpeech data: [CC BY 4.0](https://www.openslr.org/12/).
