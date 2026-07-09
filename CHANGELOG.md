# Changelog

All notable changes to this project will be documented in this file.

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
