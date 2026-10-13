# Custom dataset manifests

Score your own audio against reference transcripts. The bundled corpus is `data/manifest.json` (31 LibriSpeech clips). A custom dataset is a directory that contains its own `manifest.json` and the audio files that manifest names.

The loader accepts one manifest per data directory. `dataset_id` is a field inside that file. It is not a filename, and the loader does not scan for other manifests.

## Select the directory

`load_manifest` reads `{STT_BENCH_DATA_DIR}/manifest.json`.

| `STT_BENCH_DATA_DIR` | Resolved path |
|---|---|
| unset | `{package_parent}/data` (`./data` joined to the parent of the installed `stt_bench` package) |
| relative | `{package_parent}/{value}` |
| absolute | that path, unchanged |

`package_parent` is `Path(stt_bench/settings.py).parent.parent`. For an editable install of this repository that is the repository root. The shell working directory is not used.

Set the variable in the environment of the `stt-bench` process. The CLI and `stt-bench serve` call `get_settings()`, which caches the first `Settings()` for the life of the process. A later export does not move an already-running server.

`Settings(stt_bench_data_dir=...)` in your own script does not read that cache. Pass an absolute path there if the script's location and the package parent differ.

## Manifest

UTF-8 JSON. The top-level value is an object. Unknown keys are ignored (`license` and `source_url` on the bundled manifest are not on the model).

### `DatasetManifest`

| Field | Type | Required | Default | Role |
|---|---|---|---|---|
| `dataset_id` | string | yes | | Must equal the id the command requests. The CLI default is `default`. |
| `name` | string | yes | | Printed by `dataset show`. |
| `description` | string | no | `""` | Stored. Scoring does not read it. |
| `samples` | array | yes | | Sample objects. An empty array is valid. |

### `SampleRecord`

| Field | Type | Required | Default | Role |
|---|---|---|---|---|
| `id` | string | yes | | Sample id. Integers are rejected (`Input should be a valid string`). |
| `audio_path` | string | yes | | See path resolution below. |
| `reference_text` | string | yes | | Ground truth passed to metrics and, for the mock provider, returned as the hypothesis. |
| `condition` | string | yes | | `clean` or `noisy`. Any other string, including different case, is rejected. |
| `source` | string | yes | | `librispeech` or `synthetic`. Recordings that are not LibriSpeech use `synthetic`. |
| `metadata` | object | no | `{}` | Stored. Scoring does not read it. |

Duplicate `id` values are kept. `get_sample` returns the first match. A benchmark run scores every row, including duplicates.

`source` has no third label. That is the schema in `stt_bench/models/dataset.py`.

## Path resolution

```text
(data_dir / audio_path).resolve()
```

`data_dir` is the resolved `STT_BENCH_DATA_DIR`, which is also the directory that contains `manifest.json`.

- A relative `audio_path` is joined to that directory. `clips/tone.wav` in the example resolves to `{data_dir}/clips/tone.wav` when the process working directory is somewhere else.
- An absolute `audio_path` is kept as-is. `Path` drops the left side when the right side is absolute, then `resolve()` normalizes it.
- `..` is normalized by `resolve()`. The file may sit outside the data directory. The loader does not require the path to stay inside it.

## Audio

`dataset validate` requires each resolved path to exist and to have size greater than 0. It does not check extension, codec, sample rate, or channel count.

Duration for RTF and cost comes from the file bytes (`estimate_audio_duration_s`):

1. `soundfile`, if it can open the bytes (whatever libsndfile accepts: WAV, FLAC, OGG, and the rest of that library).
2. Otherwise, if the bytes start with `RIFF`, the stdlib `wave` module.
3. Otherwise `max(len(bytes) / 16000, 0.1)`, the same figure as 128 kbps.

The mock provider does not decode audio. With the default provider config it returns `reference_text.lower()`. Any non-empty file is enough for `--provider mock`.

The other providers send those same bytes upstream with fixed assumptions:

- Whisper uploads them under the filename `audio.flac`.
- Deepgram sets `encoding=flac` when the bytes start with `fLaC`. Otherwise it sets `encoding=linear16` and `sample_rate=16000`.
- AssemblyAI uploads the raw bytes and does not set an encoding in this repo.

The bundled corpus is 16 kHz mono FLAC. The example clips are 16 kHz mono 16-bit PCM WAV.

## Text normalization before WER

`compute_wer` (`stt_bench/metrics/wer.py`) runs `normalize_text` on the reference and the hypothesis. The benchmark path leaves `strip_fillers` at its default `False`, so `um`, `uh`, `erm`, and `ah` stay in the string. Passing `strip_fillers=True` drops those four tokens; nothing in the benchmark calls it that way.

`normalize_text`:

1. Lowercase the string.
2. Expand contractions, longest key first: `don't` → `do not`, `won't` → `will not`, `can't` → `cannot`, `n't` → ` not`, `'re` → ` are`, `'ve` → ` have`, `'ll` → ` will`, `'d` → ` would`, `'m` → ` am`.
3. Replace every character that is not a Unicode word character (`\w`) or whitespace with a space. Apostrophes that step 2 did not consume become spaces, so `it's` becomes `it s`.
4. Collapse whitespace and strip.

jiwer then applies `ToLowerCase`, `RemovePunctuation`, `RemoveMultipleSpaces`, and `Strip`. After steps 1–4 those passes do not change typical text.

If the normalized reference has no words, WER is `0.0` when the normalized hypothesis is also empty, and `1.0` otherwise.

chrF is sacrebleu `CHRF(word_order=0, char_order=6).sentence_score` on the raw strings. Punctuation F1 compares the sets of characters in `.,!?;:'"-` in the raw strings. Case and punctuation still move those two scores. The mock provider only lowercases, so punctuation in `reference_text` is still present in its hypothesis.

## Run the example

`examples/custom-dataset/` holds `manifest.json`, `clips/tone.wav` (200 ms, 440 Hz), and `clips/silence.wav` (200 ms of silence). `dataset_id` is `default`, which is what the commands below request.

From an editable install of this repository, a relative data dir resolves to the repo root:

```bash
STT_BENCH_DATA_DIR=examples/custom-dataset stt-bench dataset validate
STT_BENCH_DATA_DIR=examples/custom-dataset stt-bench benchmark run --provider mock --force
```

`dataset validate` should report the dataset valid with 2 samples. The mock run completes with WER 0 because the hypothesis is the lowercased reference (`a short tone`, `a short silence`).

One sample:

```bash
STT_BENCH_DATA_DIR=examples/custom-dataset \
  stt-bench benchmark run --provider mock --sample-id tone --force
```

`--sample-id` may be repeated. Ids that are not in the manifest are dropped. If none remain, the run completes with `sample_count` 0. That is not an error.

For a directory outside the repo, or a non-editable install, pass an absolute path:

```bash
STT_BENCH_DATA_DIR=/absolute/path/to/my-set stt-bench dataset validate
STT_BENCH_DATA_DIR=/absolute/path/to/my-set stt-bench benchmark run --provider mock --force
```

### Dataset id other than `default`

`dataset show`, `dataset stats`, `dataset validate --dataset`, and `benchmark run --dataset` load the id you pass. The file's `dataset_id` must match.

`dataset list` and `samples` always load `default`. A file whose id is something else raises `Manifest dataset_id '…' != 'default'` from those two commands.

```bash
STT_BENCH_DATA_DIR=/absolute/path/to/my-set \
  stt-bench dataset validate --dataset my-set
STT_BENCH_DATA_DIR=/absolute/path/to/my-set \
  stt-bench benchmark run --dataset my-set --provider mock --force
```

`compare` and `listen` also load dataset id `default` only.

`benchmark run` does not call `dataset validate` first. Run validate before a long job.

### HTTP

Start the server with the data directory already in the environment:

```bash
STT_BENCH_DATA_DIR=examples/custom-dataset stt-bench serve
```

```bash
curl -s -X POST http://127.0.0.1:8766/api/v1/benchmark/runs \
  -H 'content-type: application/json' \
  -d '{
    "dataset_id": "default",
    "provider": "mock",
    "transport_mode": "batch",
    "provider_config": {
      "provider": "mock",
      "model": "mock-v1",
      "transport_mode": "batch"
    },
    "force": true
  }'
```

Poll `GET /api/v1/benchmark/runs/{id}`. A load failure is HTTP 404, code `DATASET_NOT_FOUND`. The message is `DATASET_NOT_FOUND: ` plus the loader error. `json.JSONDecodeError` and pydantic `ValidationError` are `ValueError` subclasses, so a bad file takes this same 404 path.

### Python

```python
from stt_bench.dataset.loader import load_manifest, validate_dataset
from stt_bench.settings import Settings

settings = Settings(stt_bench_data_dir="/absolute/path/to/examples/custom-dataset")
print(validate_dataset(settings, dataset_id="default"))
manifest = load_manifest(settings, dataset_id="default")
```

The CLI benchmark path builds a `BenchmarkRunner` the same way as `stt_bench/cli/main.py` (`ResultsStore`, `TranscriptionCache`, `TranscriptionService`, `InProcessQueue`) and calls `create_run(dataset_id=..., provider="mock", transport_mode="batch", provider_config=ProviderConfig(provider="mock", model="mock-v1", transport_mode="batch"), force=True)`.

## Errors

### Loading the file

These raise before any sample is scored. `dataset validate` does not catch them (traceback, non-zero exit). `benchmark run` wraps `FileNotFoundError` and `ValueError` as `ValueError: DATASET_NOT_FOUND: …` and also exits with a traceback.

| Exception | Message | Cause |
|---|---|---|
| `FileNotFoundError` | `Manifest not found: {path}` | `{data_dir}/manifest.json` is missing. |
| `json.JSONDecodeError` | the decode error from the stdlib | The file is not JSON. |
| `UnicodeDecodeError` | the decode error from the stdlib | The file is not UTF-8. |
| `ValueError` | `Manifest must be a JSON object, got {type}` | The top-level JSON value is not an object. A JSON array is `got list`. |
| `ValueError` | `Manifest dataset_id '{file}' != '{requested}'` | The field and the id the command asked for differ. |
| `ValidationError` | `Field required` | A required field is missing. Manifest: `dataset_id`, `name`, `samples`. Sample: `id`, `audio_path`, `reference_text`, `condition`, `source`. |
| `ValidationError` | `Input should be 'clean' or 'noisy'` | `condition` is anything else. |
| `ValidationError` | `Input should be 'librispeech' or 'synthetic'` | `source` is anything else. |
| `ValidationError` | `Input should be a valid string` | `id`, `audio_path`, `reference_text`, `dataset_id`, `name`, or `description` is not a string. |
| `ValidationError` | `Input should be a valid list` | `samples` is not a list. |

### `stt-bench dataset validate`

On success the command prints a line and exits 0. On sample problems it prints each error and exits 1. `--json` prints the dict below.

```text
{
  "dataset_id": "default",
  "sample_count": 2,
  "valid": false,
  "errors": ["…"],
  "warnings": []
}
```

`warnings` is always `[]`. The loader never appends to it.

| `errors` entry | Cause |
|---|---|
| `Missing audio: {id} -> {path}` | The resolved path does not exist. `{path}` is absolute. |
| `Empty audio file: {id}` | The file exists and its size is 0. |
| `Empty reference for sample: {id}` | `reference_text.strip()` is empty. Load still accepts that string. |

A benchmark does not run these checks up front. A missing file fails the run: status `failed`, `error` `Audio not found: {path}` (`AUDIO_NOT_FOUND`). An empty file fails with `Empty audio file` (`AUDIO_INVALID`).

`get_sample` raises `KeyError` with `Sample '{sample_id}' not found in dataset '{dataset_id}'`. That is the error from `compare` / `listen` for an unknown id on the `default` dataset.
