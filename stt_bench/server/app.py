"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from stt_bench.providers.base import list_providers
from stt_bench.server.benchmark.routes import router as benchmark_router
from stt_bench.server.benchmark.runner import BenchmarkRunner
from stt_bench.server.cache import TranscriptionCache
from stt_bench.server.health.routes import router as health_router
from stt_bench.server.queue import InProcessQueue
from stt_bench.server.results.routes import router as results_router
from stt_bench.server.results.store import ResultsStore
from stt_bench.server.transcription.routes import router as transcription_router
from stt_bench.server.transcription.service import TranscriptionService
from stt_bench.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = ResultsStore(settings.db_path)
    await store.init()

    cache = TranscriptionCache(store)
    transcription = TranscriptionService(settings, cache)
    queue = InProcessQueue(worker_count=1)
    runner = BenchmarkRunner(settings, store, transcription, queue)

    await queue.start()

    app.state.settings = settings
    app.state.store = store
    app.state.transcription_service = transcription
    app.state.queue = queue
    app.state.benchmark_runner = runner

    # Register providers
    list_providers(settings)

    yield

    await queue.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="STT Bench", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        from stt_bench.providers.base import ProviderError

        if isinstance(exc, ProviderError):
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": {"code": exc.code, "message": exc.message, "details": {}}},
            )
        raise exc

    app.include_router(health_router)
    app.include_router(transcription_router)
    app.include_router(benchmark_router)
    app.include_router(results_router)

    return app


app = create_app()
