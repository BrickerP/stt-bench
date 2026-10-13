# Local service (self-host)

stt-bench ships a **local** FastAPI service. No accounts, multi-tenant, or cloud queue.

`docker-compose.yml` defines one service, `stt-bench`. It builds the repo `Dockerfile`, publishes `8766:8766`, and mounts the named volume `stt_bench_data` at `/data`. The image command is `stt-bench serve --host 0.0.0.0 --port 8766`.

## Quick start

```bash
docker compose up --build -d
curl -s http://127.0.0.1:8766/healthz
curl -s http://127.0.0.1:8766/version
curl -s http://127.0.0.1:8766/readyz
```

Or without Docker (binds `127.0.0.1` unless you pass `--host`):

```bash
stt-bench serve --port 8766
```

The rest of this page is the Compose layout: what `/data` keeps, which env vars the image and compose file set, and how provider keys get into the container.

## Volume

```yaml
volumes:
  - stt_bench_data:/data
```

`stt_bench_data` is a Docker named volume. Compose prefixes it with the project name (usually `stt-bench_stt_bench_data`). The Dockerfile declares `VOLUME ["/data"]`.

| Path inside the container | What it is |
|---|---|
| `/data/results.db` | SQLite file from `STT_BENCH_DB_PATH`. `ResultsStore` creates the parent directory and the file on startup. Tables: `runs`, `sample_results`, `cache_entries`. |
| `/data/cache` | `STT_BENCH_CACHE_DIR`. Same volume. |

Transcription cache rows are written to `cache_entries` in `results.db` (`TranscriptionCache` → `ResultsStore`). The server does not write cache files under `/data/cache`. Both paths sit on the volume, so removing the volume drops run history and cached transcripts together.

`docker compose down` keeps the volume. `docker compose down -v` deletes it.

`STT_BENCH_DATA_DIR` (`/app/data`) and `STT_BENCH_CONFIG_DIR` (`/app/config`) are copied into the image (`COPY data`, `COPY config`). They are not on `stt_bench_data`. Replacing the container does not drop the bundled corpus or the shipped `pricing.yaml` / `scoring_weights.yaml`. A write from `PUT /api/v1/scoring/weights` lands in the container filesystem and disappears when that container is removed, unless you bind-mount config (below).

## Environment

Compose sets these on the service. The Dockerfile `ENV` lines use the same path and port defaults. Outside Docker, `Settings` defaults are the host paths in `.env.example` (`127.0.0.1`, `./data/results.db`, `./data/cache`, `./data`, `./config`).

| Variable | Compose / image value | Role |
|---|---|---|
| `STT_BENCH_HOST` | `0.0.0.0` | Returned by `GET /api/v1/config`. The process listen address is the image command `--host 0.0.0.0`, not this variable. |
| `STT_BENCH_PORT` | `8766` | Returned by `GET /api/v1/config`. The listen port is the image command `--port 8766`, published as `8766:8766`. |
| `STT_BENCH_DB_PATH` | `/data/results.db` | SQLite path on the named volume. |
| `STT_BENCH_CACHE_DIR` | `/data/cache` | Configured cache directory on the named volume. Live cache rows are in `results.db` (see above). |
| `STT_BENCH_DATA_DIR` | `/app/data` | Dataset directory. The image ships `data/manifest.json` and the bundled audio here. |
| `STT_BENCH_CONFIG_DIR` | `/app/config` | `pricing.yaml` and `scoring_weights.yaml`. |
| `OPENAI_API_KEY` | empty if unset | Whisper. Injected from the shell or a `.env` file next to the compose file. |
| `DEEPGRAM_API_KEY` | empty if unset | Deepgram. Same injection. |
| `ASSEMBLYAI_API_KEY` | empty if unset | AssemblyAI. Same injection. |
| `GOOGLE_APPLICATION_CREDENTIALS` | empty if unset | Google Speech service-account JSON path. The file must exist at that path inside the container. |
| `AZURE_SPEECH_KEY` | empty if unset | Azure Speech key. Same injection. |
| `AZURE_SPEECH_REGION` | empty if unset | Azure Speech region, for example `eastus`. |

Changing `STT_BENCH_HOST` or `STT_BENCH_PORT` in the environment block does not move the bind. The Dockerfile `CMD` passes `--host` and `--port` to `stt-bench serve`, and those flags are what uvicorn uses. To listen elsewhere, change the command and the `ports:` mapping together.

`.env.example` also lists `WHISPER_RPM`, `DEEPGRAM_RPM`, `WHISPER_MODEL`, `DEEPGRAM_MODEL`, `ASSEMBLYAI_MODEL`, `GOOGLE_SPEECH_MODEL`, `AZURE_SPEECH_MODEL`, and `STT_BENCH_LOG_LEVEL`. Those are real settings for a host `stt-bench` process. This compose file does not forward them. A value in `.env` reaches the container only when the compose file interpolates it (the provider credentials below) or you add an `environment:` entry.

## Provider API keys

Keys are read from the process environment (`OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ASSEMBLYAI_API_KEY`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `GOOGLE_APPLICATION_CREDENTIALS`). The service does not write them to SQLite. The Dockerfile does not copy a `.env` into the image.

Compose interpolates them with an empty default:

```yaml
OPENAI_API_KEY: "${OPENAI_API_KEY:-}"
DEEPGRAM_API_KEY: "${DEEPGRAM_API_KEY:-}"
ASSEMBLYAI_API_KEY: "${ASSEMBLYAI_API_KEY:-}"
GOOGLE_APPLICATION_CREDENTIALS: "${GOOGLE_APPLICATION_CREDENTIALS:-}"
AZURE_SPEECH_KEY: "${AZURE_SPEECH_KEY:-}"
AZURE_SPEECH_REGION: "${AZURE_SPEECH_REGION:-}"
```

Either of these supplies the values. Compose reads `.env` from the project directory (next to `docker-compose.yml`) for interpolation. A shell export of the same name wins over `.env`.

```bash
cp .env.example .env   # then replace the key placeholders; .env is gitignored
docker compose up --build -d
```

```bash
export OPENAI_API_KEY=...
export DEEPGRAM_API_KEY=...
export ASSEMBLYAI_API_KEY=...
export AZURE_SPEECH_KEY=...
export AZURE_SPEECH_REGION=eastus
docker compose up --build -d
```

`GOOGLE_APPLICATION_CREDENTIALS` is a filesystem path, not a key string. Compose will pass the host path through, which is wrong inside the container unless you bind-mount the JSON and point the variable at the container path. Add the bind next to `stt_bench_data` (do not drop the named volume). Do not commit the JSON.

```yaml
services:
  stt-bench:
    environment:
      GOOGLE_APPLICATION_CREDENTIALS: /secrets/gcp-sa.json
    volumes:
      - stt_bench_data:/data
      - /absolute/path/on/the/host/sa.json:/secrets/gcp-sa.json:ro
```

Mock runs do not need keys. `GET /readyz` reports each key as `configured` or `missing`. Readiness is `ready` when the dataset validates and `degraded` when it does not. A missing key does not by itself mark the process degraded.

## Optional bind mounts

Keep `stt_bench_data:/data`. Add a bind only for a path you want to replace.

Custom dataset. `STT_BENCH_DATA_DIR` must be the directory that contains `manifest.json`. An absolute path is used as-is ([custom datasets](./custom-datasets.md)).

```yaml
services:
  stt-bench:
    environment:
      STT_BENCH_DATA_DIR: /datasets/mine
    volumes:
      - stt_bench_data:/data
      - /absolute/path/to/my-set:/datasets/mine:ro
```

Config you want to edit and keep. The repo `config/` directory is the same pair of YAML files the image copies to `/app/config`.

```yaml
volumes:
  - stt_bench_data:/data
  - ./config:/app/config
```

Host directory instead of the named volume, if you want `results.db` on the host filesystem. Do not mount this over `/app/data`.

```yaml
volumes:
  - ./runtime-data:/data
```

`STT_BENCH_DB_PATH` stays `/data/results.db`. A database path outside `/data` is not on the volume.

## Verify

From the directory that contains `docker-compose.yml`:

```bash
docker compose up --build -d
curl -s http://127.0.0.1:8766/healthz
curl -s http://127.0.0.1:8766/readyz
curl -s http://127.0.0.1:8766/version
```

`/healthz` returns `{"status":"ok"}`. `/version` returns `name` `stt-eval-bench` and `cli` `stt-bench`. `/readyz` returns `status` `ready` when `data/manifest.json` in the image validates.

Start a mock run against that bundled dataset. `provider_config.model` for mock is `mock-v1`. `force: true` skips the cache lookup and overwrites the `cache_entries` row.

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

The response is HTTP 202 with `id` and `poll_url` (`/api/v1/benchmark/runs/{id}`). Poll that URL until `status` is `completed`.

The markdown report reads `STT_BENCH_DB_PATH` in the process that runs it. Inside the container that path is `/data/results.db` on the volume:

```bash
docker compose exec stt-bench stt-bench report --format markdown
```

`stt-bench report` on the host reads the host default `./data/results.db` (or whatever `STT_BENCH_DB_PATH` is in that shell). It does not open the named volume.

Leaderboard for the same store: `GET /api/v1/results/leaderboard`.

## Endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness |
| `GET /readyz` | Readiness + key/dataset checks |
| `GET /version` | Package / CLI version |
| `GET /api/v1/providers` | Registered providers |
| `GET /api/v1/datasets` | Datasets |
| `POST /api/v1/benchmark/runs` | Start a run (see OpenAPI) |
| `GET /api/v1/results/leaderboard` | Leaderboard |

Interactive OpenAPI: `http://127.0.0.1:8766/docs`

## Mock benchmark on the host

This path uses the host process and the host database, not the Compose volume:

```bash
stt-bench benchmark run --provider mock --force
stt-bench report --format markdown --out report.md
```

Architecture details: [DESIGN.md](../DESIGN.md). Maturity gate: [OSS_MATURITY.md](./OSS_MATURITY.md).
