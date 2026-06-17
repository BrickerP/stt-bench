"""SQLite persistence for runs, results, and cache."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from stt_bench.models.benchmark import AggregateMetrics, BenchmarkRun, BenchmarkRunConfig, SampleMetrics
from stt_bench.models.transcription import LeaderboardEntry, TranscriptionResult


class ResultsStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    sample_count INTEGER,
                    aggregate_metrics_json TEXT,
                    vibe_score REAL,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS sample_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sample_id TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    transcription_json TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    audio_hash TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_sample_results_run ON sample_results(run_id);
                """
            )
            await db.commit()

    async def save_run(self, run: BenchmarkRun) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO runs
                (id, status, config_json, created_at, completed_at, sample_count,
                 aggregate_metrics_json, vibe_score, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.status,
                    run.config.model_dump_json(),
                    run.created_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.sample_count,
                    run.aggregate_metrics.model_dump_json() if run.aggregate_metrics else None,
                    run.vibe_score,
                    run.error,
                ),
            )
            await db.commit()

    async def get_run(self, run_id: str) -> BenchmarkRun | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return self._row_to_run(row)

    async def list_runs(self, limit: int = 50, offset: int = 0) -> list[BenchmarkRun]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        return [self._row_to_run(r) for r in rows]

    async def save_sample_result(
        self,
        run_id: str,
        sample_id: str,
        metrics: SampleMetrics,
        transcription: TranscriptionResult | None = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sample_results (run_id, sample_id, metrics_json, transcription_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    sample_id,
                    metrics.model_dump_json(),
                    transcription.model_dump_json() if transcription else None,
                ),
            )
            await db.commit()

    async def get_sample_results(self, run_id: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sample_results WHERE run_id = ? ORDER BY id",
                (run_id,),
            ) as cur:
                rows = await cur.fetchall()
        results = []
        for row in rows:
            results.append({
                "sample_id": row["sample_id"],
                "metrics": json.loads(row["metrics_json"]),
                "transcription": json.loads(row["transcription_json"]) if row["transcription_json"] else None,
            })
        return results

    async def get_cache(self, cache_key: str) -> TranscriptionResult | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT result_json FROM cache_entries WHERE cache_key = ?",
                (cache_key,),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return TranscriptionResult.model_validate_json(row["result_json"])

    async def set_cache(
        self,
        cache_key: str,
        provider: str,
        audio_hash: str,
        config_hash: str,
        result: TranscriptionResult,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cache_entries
                (cache_key, provider, audio_hash, config_hash, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    provider,
                    audio_hash,
                    config_hash,
                    result.model_dump_json(),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()

    async def get_transcription_by_id(self, result_id: str) -> TranscriptionResult | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT result_json FROM cache_entries WHERE result_json LIKE ?",
                (f'%"id": "{result_id}"%',),
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        result = TranscriptionResult.model_validate_json(row["result_json"])
        if result.id == result_id:
            return result
        return None

    async def leaderboard(
        self,
        dataset_id: str | None = None,
        limit: int = 10,
        exclude_mock: bool = False,
    ) -> list[LeaderboardEntry]:
        runs = await self.list_runs(limit=200)
        entries: list[LeaderboardEntry] = []
        for run in runs:
            if run.status != "completed" or run.vibe_score is None or not run.aggregate_metrics:
                continue
            if exclude_mock and run.config.provider == "mock":
                continue
            if dataset_id and run.config.dataset_id != dataset_id:
                continue
            entries.append(
                LeaderboardEntry(
                    rank=0,
                    run_id=run.id,
                    provider=run.config.provider,
                    transport_mode=run.config.transport_mode,
                    vibe_score=run.vibe_score,
                    wer_mean=run.aggregate_metrics.wer_mean,
                    chrf_mean=run.aggregate_metrics.chrf_mean,
                    ttft_p50_ms=run.aggregate_metrics.ttft_p50_ms,
                    cost_total_usd=run.aggregate_metrics.cost_total_usd,
                    dataset_id=run.config.dataset_id,
                    created_at=run.created_at,
                )
            )
        entries.sort(key=lambda e: e.vibe_score, reverse=True)
        for i, e in enumerate(entries[:limit]):
            e.rank = i + 1
        return entries[:limit]

    def _row_to_run(self, row: aiosqlite.Row) -> BenchmarkRun:
        agg = None
        if row["aggregate_metrics_json"]:
            agg = AggregateMetrics.model_validate_json(row["aggregate_metrics_json"])
        return BenchmarkRun(
            id=row["id"],
            status=row["status"],
            config=BenchmarkRunConfig.model_validate_json(row["config_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            sample_count=row["sample_count"] or 0,
            aggregate_metrics=agg,
            vibe_score=row["vibe_score"],
            error=row["error"],
        )
