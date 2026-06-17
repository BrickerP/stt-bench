"""In-process benchmark job queue."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine

from stt_bench.models.config import ProviderConfig


@dataclass
class BenchmarkJob:
    run_id: str
    dataset_id: str
    provider: str
    transport_mode: str
    config: ProviderConfig
    sample_ids: list[str] | None = None
    force: bool = False


@dataclass
class ProgressEvent:
    run_id: str
    event_type: str  # started, sample_done, completed, failed
    sample_id: str | None = None
    progress: float = 0.0
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class InProcessQueue:
    def __init__(self, worker_count: int = 1):
        self._queue: asyncio.Queue[BenchmarkJob | None] = asyncio.Queue()
        self._events: dict[str, asyncio.Queue[ProgressEvent]] = {}
        self._worker_count = worker_count
        self._workers: list[asyncio.Task] = []
        self._handler: Callable[[BenchmarkJob], Coroutine[Any, Any, None]] | None = None
        self._started = False

    def set_handler(self, handler: Callable[[BenchmarkJob], Coroutine[Any, Any, None]]) -> None:
        self._handler = handler

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for _ in range(self._worker_count):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        for _ in range(self._worker_count):
            await self._queue.put(None)
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._started = False

    async def enqueue(self, job: BenchmarkJob) -> None:
        self._events.setdefault(job.run_id, asyncio.Queue())
        await self._queue.put(job)

    def get_event_queue(self, run_id: str) -> asyncio.Queue[ProgressEvent]:
        return self._events.setdefault(run_id, asyncio.Queue())

    async def emit(self, event: ProgressEvent) -> None:
        q = self._events.get(event.run_id)
        if q:
            await q.put(event)

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            if job is None:
                break
            if self._handler:
                await self._handler(job)
            self._queue.task_done()
