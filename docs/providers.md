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

Google and Azure follow that same batch contract:

- `stt_bench/providers/google.py`, `tests/test_google_contract.py`
- `stt_bench/providers/azure.py`, `tests/test_azure_contract.py`

## Mock interim script

The mock provider grows the reference one word at a time unless `ProviderConfig.extra["interim_script"]` is a list of strings. Those strings are emitted as non-final partials, in order, and then the final transcript is emitted. The script is deterministic (fixed confidence, no network) so partial revision rate can be scored in CI.

```python
extra = {"interim_script": ["the cat sat", "the dog sat"], "latency_ms": 0, "reference_text": "the dog sat"}
```

## Google Cloud Speech-to-Text

Batch only. `transcribe_stream` raises `TransportNotSupported`.

Auth is `GOOGLE_APPLICATION_CREDENTIALS`: a service account JSON file. Cloud Speech-to-Text v1 REST (`speech:recognize`) requires an OAuth bearer token with the `cloud-platform` scope. This adapter exchanges that file for a token (google-auth) and posts audio with httpx. It does not read an API key and it does not depend on `google-cloud-speech`.

`validate_config` checks the file locally (JSON object with `client_email` and `private_key`). It does not call Google. The token exchange runs on transcribe.

Audio up to 60 seconds uses `speech:recognize`. Longer audio uses `speech:longrunningrecognize` and polls the operation. Inline content over 10 MB is rejected in-process. Google may still reject inline audio longer than one minute (that path expects a `gs://` URI); the adapter surfaces the upstream error. Clips in `data/librispeech/` are short enough for `speech:recognize`.

Default model is `latest_long` (`GOOGLE_SPEECH_MODEL`). WAV and FLAC are sent with their headers so Google reads encoding and sample rate.

## Azure Speech

Batch only. `transcribe_stream` raises `TransportNotSupported`.

Auth is `AZURE_SPEECH_KEY` plus `AZURE_SPEECH_REGION` (for example `eastus`). The adapter posts multipart audio to fast transcription:

`https://{region}.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?api-version=2025-10-15`

`validate_config` checks that the key and region are present. It does not call Azure. The model field (`AZURE_SPEECH_MODEL`, default `fast`) selects the pricing row. The fast-transcription request does not send a model id.

## Manual smoke (local only)

Do not put these keys in CI.

```bash
export ASSEMBLYAI_API_KEY=...
stt-bench transcribe file data/librispeech/1089-134686-0000.flac --provider assemblyai --force
```

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
stt-bench transcribe file data/librispeech/1089-134686-0000.flac --provider google --mode batch --force
```

```bash
export AZURE_SPEECH_KEY=...
export AZURE_SPEECH_REGION=eastus
stt-bench transcribe file data/librispeech/1089-134686-0000.flac --provider azure --mode batch --force
```

For Docker, mount the service account JSON and set `GOOGLE_APPLICATION_CREDENTIALS` to the path inside the container. See [service.md](./service.md).
