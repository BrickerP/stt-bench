"""Benchmark REST routes."""

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from stt_bench.models.config import ProviderConfig
from stt_bench.server.benchmark.runner import BenchmarkRunner
from stt_bench.server.errors import APIError

router = APIRouter(prefix="/api/v1/benchmark", tags=["benchmark"])


class CreateRunRequest(BaseModel):
    dataset_id: str = "default"
    provider: str
    transport_mode: str = "batch"
    provider_config: ProviderConfig
    sample_ids: list[str] | None = None
    force: bool = False


def _runner(request: Request) -> BenchmarkRunner:
    return request.app.state.benchmark_runner


@router.post("/runs", status_code=202)
async def create_run(body: CreateRunRequest, request: Request):
    runner = _runner(request)
    try:
        run = await runner.create_run(
            dataset_id=body.dataset_id,
            provider=body.provider,
            transport_mode=body.transport_mode,
            provider_config=body.provider_config,
            sample_ids=body.sample_ids,
            force=body.force,
        )
    except ValueError as e:
        if "DATASET_NOT_FOUND" in str(e):
            raise APIError("DATASET_NOT_FOUND", str(e), 404) from e
        raise

    return {
        "id": run.id,
        "status": run.status,
        "sample_count": run.sample_count,
        "poll_url": f"/api/v1/benchmark/runs/{run.id}",
    }


@router.get("/runs")
async def list_runs(request: Request, limit: int = 50, offset: int = 0):
    store = request.app.state.store
    runs = await store.list_runs(limit=limit, offset=offset)
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    store = request.app.state.store
    run = await store.get_run(run_id)
    if not run:
        raise APIError("RUN_NOT_FOUND", f"Run not found: {run_id}", 404)
    return run


@router.get("/runs/{run_id}/samples")
async def get_run_samples(run_id: str, request: Request):
    store = request.app.state.store
    run = await store.get_run(run_id)
    if not run:
        raise APIError("RUN_NOT_FOUND", f"Run not found: {run_id}", 404)
    samples = await store.get_sample_results(run_id)
    return {"run_id": run_id, "samples": samples}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    queue = request.app.state.queue
    event_q = queue.get_event_queue(run_id)

    async def generator():
        while True:
            event = await event_q.get()
            yield {
                "event": event.event_type,
                "data": json.dumps({
                    "run_id": event.run_id,
                    "sample_id": event.sample_id,
                    "progress": event.progress,
                    "message": event.message,
                    "data": event.data,
                }),
            }
            if event.event_type in ("completed", "failed"):
                break

    return EventSourceResponse(generator())


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str, request: Request):
    store = request.app.state.store
    run = await store.get_run(run_id)
    if not run:
        raise APIError("RUN_NOT_FOUND", f"Run not found: {run_id}", 404)
    if run.status == "completed":
        raise APIError("RUN_ALREADY_COMPLETE", "Run already completed", 409)
    run.status = "cancelled"
    await store.save_run(run)
    return {"id": run_id, "status": "cancelled"}
