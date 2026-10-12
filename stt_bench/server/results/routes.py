"""Results and leaderboard routes."""

import json

from fastapi import APIRouter, Request, UploadFile

from stt_bench.models.benchmark import BenchmarkRun
from stt_bench.scoring.vibe import ScoringWeights, load_scoring_weights, save_scoring_weights
from stt_bench.server.errors import APIError

router = APIRouter(prefix="/api/v1", tags=["results"])


@router.get("/results/leaderboard")
async def leaderboard(request: Request, dataset_id: str | None = None, limit: int = 10):
    store = request.app.state.store
    entries = await store.leaderboard(dataset_id=dataset_id, limit=limit)
    return {"entries": entries}


@router.get("/results/runs/{run_id}/export")
async def export_run(run_id: str, request: Request):
    store = request.app.state.store
    run = await store.get_run(run_id)
    if not run:
        raise APIError("RUN_NOT_FOUND", f"Run not found: {run_id}", 404)
    samples = await store.get_sample_results(run_id)
    lines = [{"run": run.model_dump(mode="json"), "samples": samples}]
    content = "\n".join(json.dumps(line) for line in lines)
    return {"format": "jsonl", "content": content}


@router.post("/results/import")
async def import_run(file: UploadFile, request: Request):
    store = request.app.state.store
    text = (await file.read()).decode()
    for line in text.strip().split("\n"):
        data = json.loads(line)
        run = BenchmarkRun.model_validate(data["run"])
        await store.save_run(run)
    return {"imported": True}


@router.post("/metrics/compute")
async def compute_metrics(body: dict):
    from stt_bench.metrics.compute import compute_sample_metrics

    timings = body.get("timings", {})
    sm = compute_sample_metrics(
        sample_id="adhoc",
        reference=body["reference"],
        hypothesis=body["hypothesis"],
        ttft_ms=timings.get("ttft_ms"),
        total_ms=timings.get("total_ms", 0),
        audio_duration_s=timings.get("audio_duration_s", 1.0),
        cost_usd=body.get("cost_usd"),
    )
    return {
        "wer": sm.wer,
        "wer_details": sm.wer_details.model_dump(),
        "chrf": sm.chrf,
        "punctuation_f1": sm.punctuation_f1,
        "rtf": sm.rtf,
    }


@router.get("/metrics/normalize")
async def normalize(reference: str = "", hypothesis: str = ""):
    from stt_bench.metrics.wer import normalize_text

    return {
        "reference_normalized": normalize_text(reference),
        "hypothesis_normalized": normalize_text(hypothesis),
    }


@router.post("/scoring/vibe")
async def scoring_vibe(body: dict, request: Request):
    from stt_bench.models.benchmark import AggregateMetrics
    from stt_bench.scoring.vibe import compute_vibe_score

    settings = request.app.state.settings
    metrics = AggregateMetrics(**body["metrics"])
    vibe = compute_vibe_score(
        metrics,
        body.get("transport_mode", "batch"),
        config_dir=str(settings.config_dir),
    )
    return vibe


@router.get("/scoring/weights")
async def get_weights(request: Request):
    settings = request.app.state.settings
    return load_scoring_weights(str(settings.config_dir))


@router.put("/scoring/weights")
async def put_weights(weights: ScoringWeights, request: Request):
    settings = request.app.state.settings
    save_scoring_weights(str(settings.config_dir), weights)
    return weights


@router.get("/datasets")
async def list_datasets(request: Request):
    from stt_bench.dataset.loader import list_datasets

    return {"datasets": list_datasets(request.app.state.settings)}


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, request: Request):
    from stt_bench.dataset.loader import get_dataset_stats, load_manifest

    settings = request.app.state.settings
    try:
        load_manifest(settings, dataset_id)
    except (FileNotFoundError, ValueError):
        raise APIError("DATASET_NOT_FOUND", f"Dataset '{dataset_id}' not found", 404)
    return get_dataset_stats(settings, dataset_id)


@router.get("/datasets/{dataset_id}/samples")
async def dataset_samples(dataset_id: str, request: Request, limit: int = 100, offset: int = 0):
    from stt_bench.dataset.loader import load_manifest

    settings = request.app.state.settings
    manifest = load_manifest(settings, dataset_id)
    samples = manifest.samples[offset : offset + limit]
    return {"samples": samples, "total": len(manifest.samples)}


@router.get("/datasets/{dataset_id}/samples/{sample_id}")
async def dataset_sample(dataset_id: str, sample_id: str, request: Request):
    from stt_bench.dataset.loader import get_sample

    try:
        sample = get_sample(dataset_id, sample_id, request.app.state.settings)
    except KeyError:
        raise APIError("DATASET_NOT_FOUND", f"Sample '{sample_id}' not found", 404)
    return sample


@router.get("/providers")
async def list_providers_route(request: Request):
    from stt_bench.providers.base import list_providers

    providers = list_providers(request.app.state.settings)
    return {
        "providers": [
            {
                "name": p.name,
                "display_name": p.display_name,
                "capabilities": p.capabilities.model_dump(),
                "default_config": p.default_config().model_dump()
                if hasattr(p, "default_config")
                else {},
            }
            for p in providers
        ]
    }


@router.get("/providers/{name}")
async def get_provider_route(name: str, request: Request):
    from stt_bench.providers.base import ProviderError, get_provider

    try:
        p = get_provider(name, request.app.state.settings)
    except ProviderError:
        raise APIError("PROVIDER_NOT_FOUND", f"Provider '{name}' not found", 404)
    return {
        "name": p.name,
        "display_name": p.display_name,
        "capabilities": p.capabilities.model_dump(),
        "default_config": p.default_config().model_dump() if hasattr(p, "default_config") else {},
    }


class ValidateProviderRequest(dict):
    pass


@router.post("/providers/{name}/validate")
async def validate_provider(name: str, body: dict, request: Request):
    from stt_bench.models.config import ProviderConfig
    from stt_bench.providers.base import ProviderError, get_provider

    config = ProviderConfig.model_validate(body.get("config", {"provider": name, "model": "default"}))
    try:
        p = get_provider(name, request.app.state.settings)
        await p.validate_config(config)
    except ProviderError as e:
        raise APIError(e.code, e.message, e.status_code)
    return {"valid": True, "message": "API key accepted"}
