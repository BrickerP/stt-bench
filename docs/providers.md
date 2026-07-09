# Adding a provider adapter

## Contract

Implement `STTProvider` in `stt_bench/providers/` and decorate with `@register_provider`:

- `name`, `display_name`, `capabilities`
- `validate_config`
- `transcribe_batch` and/or `transcribe_stream`
- `estimate_cost_usd`
- `default_config` (recommended)

Register the class so `list_providers` / `get_provider` see it (import side-effect via `@register_provider` + `_ensure_providers_registered` in `base.py`).

Add the provider name to `ProviderConfig.provider` Literal in `stt_bench/models/config.py`.

Add pricing under `config/pricing.yaml`.

## Tests (required for CI)

CI must **not** use real API keys. Add contract tests that:

- assert registration and capabilities
- assert unsupported transport raises `TransportNotSupported`
- assert missing key fails validation

Live smoke tests belong in docs or a manual `workflow_dispatch` job.

## Example

See `stt_bench/providers/assemblyai.py` and `tests/test_assemblyai_contract.py`.

## Manual smoke (local only)

```bash
export ASSEMBLYAI_API_KEY=...
stt-bench transcribe file data/librispeech/1089-134686-0000.flac --provider assemblyai --force
```
