# Contributing to stt-bench

Thanks for helping improve this STT evaluation toolkit.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # optional; use --provider mock without keys
pytest -q
ruff check stt_bench tests
```

## Pull requests

1. Open an issue first for non-trivial changes (new provider, metric, dataset).
2. Keep PRs focused; add tests for new behavior.
3. CI must stay green: `pytest`, `ruff`, package build.
4. Do **not** commit API keys or `.env`.
5. Real provider smoke tests are manual only — CI uses mock/fixtures/contracts.

## Good first contributions

- Add a provider adapter (see [docs/providers.md](docs/providers.md))
- Improve report formatting
- Expand dataset manifests
- Docs / examples

## Code style

- Python 3.11+
- Ruff for lint
- Prefer extending existing modules over new abstraction layers
