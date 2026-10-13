# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- README mock-bench demo (`docs/assets/demo-mock-bench.gif`): a terminal recording of `benchmark run --provider mock`, a markdown report snippet, and `results leaderboard`. Regenerate with `python docs/assets/render_demo_gif.py` (see `docs/assets/README.md`).
- Google Cloud Speech-to-Text and Azure Speech batch adapters (`google`, `azure`). CI runs contract tests only; live smoke is manual (`docs/providers.md`).
- Pull request mock benchmark publishes `report.md` on the job summary and as the `stt-bench-report` artifact, and updates one sticky pull request comment. Fork pull requests skip the comment. Set the repository variable `STT_BENCH_PR_COMMENT` to `false` to opt out.
- Partial revision rate for streaming providers: fraction of interim updates that rewrite previously emitted words, plus revised-word count and word churn normalized by final length. Batch runs report the metric as not applicable. The mock provider accepts `extra.interim_script` for a deterministic interim sequence.
- `docs/custom-datasets.md`: manifest fields, path resolution, WER normalization, and the CLI / HTTP calls for a user-supplied dataset
- `examples/custom-dataset/`: two short WAV clips and a manifest that `stt-bench benchmark run --provider mock` can score without API keys

### Changed

- `reports/examples/mock-report.md` refreshed from the mock run in the README demo, including the revision and churn columns
- `docs/service.md`: named volume `stt_bench_data`, env vars, and provider-key injection for `docker compose` self-host
- `confidence.partial_revision_rate` uses the same prefix-stability definition as the benchmark metric. It is null when no interim update was observed, rather than zero.

### Fixed

- A manifest whose top-level JSON value is not an object raises `ValueError` (`Manifest must be a JSON object, got …`) instead of `AttributeError`
- Manifest files are decoded as UTF-8

## [0.1.1] — 2026-07-09

### Added

- First PyPI publish of `stt-eval-bench` via Trusted Publishing (pending publisher → live project)

### Notes

- Install: `pip install stt-eval-bench`
- CLI remains `stt-bench`

## [0.1.0] — 2026-07-09

### Added

- Maintainer-grade OSS surface: CI, governance docs, Docker local service, markdown reports
- Package publish name `stt-eval-bench` (PyPI name `stt-bench` was already taken)
- AssemblyAI provider adapter with contract/mock tests
- `stt-bench report --format markdown` for PR-pasteable benchmark summaries
- `/healthz`, `/readyz`, `/version` service endpoints
- docs/OSS_MATURITY.md execution gate + service/providers docs + examples

### Notes

- CLI entrypoint remains `stt-bench`
- CI remains mock-only; real provider smoke tests are manual
