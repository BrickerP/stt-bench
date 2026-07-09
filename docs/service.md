# Local service (self-host)

stt-bench ships a **local** FastAPI service. No accounts, multi-tenant, or cloud queue.

## Quick start

```bash
docker compose up --build -d
curl -s http://127.0.0.1:8766/healthz
curl -s http://127.0.0.1:8766/version
curl -s http://127.0.0.1:8766/readyz
```

Or without Docker:

```bash
stt-bench serve --port 8766
```

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

## Secrets

Provider API keys are read from environment variables only (`OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ASSEMBLYAI_API_KEY`). They are never uploaded or persisted by the service.

## Mock benchmark via API/CLI

```bash
stt-bench benchmark run --provider mock --force
stt-bench report --format markdown --out report.md
```

Architecture details: [DESIGN.md](../DESIGN.md). Maturity gate: [OSS_MATURITY.md](./OSS_MATURITY.md).
