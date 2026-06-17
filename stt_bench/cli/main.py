"""CLI entry point — see DESIGN.md for full command tree."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Annotated, Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from stt_bench.models.config import ProviderConfig
from stt_bench.settings import get_settings

console = Console()
err_console = Console(stderr=True)
app = typer.Typer(
    name="stt-bench",
    help="Benchmark Whisper (batch) vs Deepgram (streaming) for dictation.",
    no_args_is_help=True,
)

# Global state via callback
_state: dict = {"api_url": "http://127.0.0.1:8766", "json_output": False, "verbose": False, "math": False}


@app.callback()
def main(
    api_url: Annotated[str, typer.Option("--api-url", help="API base URL")] = "http://127.0.0.1:8766",
    json_output: Annotated[bool, typer.Option("--json", help="JSON output")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Verbose")] = False,
    math: Annotated[bool, typer.Option("--math", help="Show metric formulas (with command output or alone)")] = False,
):
    _state["api_url"] = api_url.rstrip("/")
    _state["json_output"] = json_output
    _state["verbose"] = verbose
    _state["math"] = math


def _maybe_print_math():
    if _state["math"]:
        from stt_bench.math_doc import print_math_doc

        console.print()
        print_math_doc(console)


def _print_json(data):
    console.print_json(json.dumps(data, default=str))


def _fmt_pct(v: float | None) -> str:
    return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "—"


def _fmt_chrf(v: float | None) -> str:
    return f"{v:.1f}" if isinstance(v, (int, float)) else "—"


def _api_client() -> httpx.Client:
    return httpx.Client(base_url=_state["api_url"], timeout=300.0)


# --- serve ---

@app.command("math")
def math_cmd():
    """Print all metric and scoring formulas."""
    from stt_bench.math_doc import print_math_doc

    print_math_doc(console)


# --- compare / listen / samples (easy testing) ---

DEFAULT_NOISY_SAMPLE = "1089-134686-0000_noisy"


@app.command("samples")
def samples_list(
    condition: Optional[str] = typer.Option(None, "--condition", help="Filter: clean or noisy"),
):
    """List available audio samples in the dataset."""
    from stt_bench.dataset.loader import load_manifest, resolve_audio_path

    settings = get_settings()
    manifest = load_manifest(settings)
    rows = manifest.samples
    if condition:
        rows = [s for s in rows if s.condition == condition]

    if _state["json_output"]:
        _print_json(
            [
                {
                    "id": s.id,
                    "condition": s.condition,
                    "audio_path": str(resolve_audio_path(s, settings)),
                    "reference_preview": s.reference_text[:80] + ("…" if len(s.reference_text) > 80 else ""),
                }
                for s in rows
            ]
        )
        return

    table = Table(title=f"Dataset samples ({len(rows)} of {len(manifest.samples)})")
    table.add_column("ID")
    table.add_column("Condition")
    table.add_column("Audio")
    for s in rows:
        table.add_row(s.id, s.condition, str(resolve_audio_path(s, settings)))
    console.print(table)
    console.print(
        "\n[dim]30 clean clips in data/librispeech/ · 1 noisy clip in data/noisy/[/dim]"
    )


async def _transcribe_sample_metrics(provider: str, audio_path: Path, reference: str, sample_id: str):
    from stt_bench.metrics.compute import compute_sample_metrics
    from stt_bench.metrics.cost import estimate_provider_cost
    from stt_bench.models.benchmark import AggregateMetrics
    from stt_bench.scoring.vibe import compute_vibe_score
    from stt_bench.server.cache import TranscriptionCache
    from stt_bench.server.results.store import ResultsStore
    from stt_bench.server.transcription.service import TranscriptionService

    settings = get_settings()
    store = ResultsStore(settings.db_path)
    await store.init()
    svc = TranscriptionService(settings, TranscriptionCache(store))

    mode = _default_mode(provider)
    config = ProviderConfig(
        provider=provider,  # type: ignore
        model=_default_model(provider, settings),
        transport_mode=mode,  # type: ignore
    )
    result = await svc.transcribe_path(audio_path, provider, config, force=True, reference_text=reference)
    cost = estimate_provider_cost(provider, config.model, result.audio_duration_s, settings)
    metrics = compute_sample_metrics(
        sample_id=sample_id,
        reference=reference,
        hypothesis=result.text or "",
        ttft_ms=result.timings.ttft_ms,
        total_ms=result.timings.total_ms,
        audio_duration_s=result.audio_duration_s,
        cost_usd=cost,
        confidence_mean=result.confidence.mean if result.confidence else None,
    )
    agg = AggregateMetrics(
        wer_mean=metrics.wer,
        wer_median=metrics.wer,
        ttft_p50_ms=metrics.ttft_ms,
        ttft_p95_ms=metrics.ttft_ms,
        total_ms_p50=metrics.total_ms,
        total_ms_p95=metrics.total_ms,
        rtf_mean=metrics.rtf,
        cost_total_usd=cost,
        cost_per_minute_usd=(cost / (result.audio_duration_s / 60)) if result.audio_duration_s else 0,
        sample_count=1,
    )
    vibe = compute_vibe_score(agg, mode, config_dir=str(settings.config_dir))
    return result, metrics, vibe


@app.command("compare")
def compare_cmd(
    sample_id: str = typer.Argument(DEFAULT_NOISY_SAMPLE, help="Sample ID from `stt-bench samples`"),
    all_samples: bool = typer.Option(False, "--all", help="Run on entire dataset (31 clips)"),
):
    """Compare Whisper vs Deepgram on one sample (default: noisy clip)."""
    settings = get_settings()
    _validate_provider_credentials(["whisper", "deepgram"], settings)

    if all_samples:
        benchmark_run(
            dataset="default",
            provider=None,
            providers=["whisper", "deepgram"],
            mode=None,
            sample_id=None,
            force=True,
            wait=True,
            local=True,
            verbose=True,
        )
        results_leaderboard(exclude_mock=True, top=10, limit=None, dataset="default")
        _maybe_print_math()
        return

    from stt_bench.dataset.loader import get_sample, resolve_audio_path

    sample = get_sample("default", sample_id, settings)
    audio_path = resolve_audio_path(sample, settings)

    async def _run():
        return await asyncio.gather(
            _transcribe_sample_metrics("whisper", audio_path, sample.reference_text, sample_id),
            _transcribe_sample_metrics("deepgram", audio_path, sample.reference_text, sample_id),
            return_exceptions=True,
        )

    results = asyncio.run(_run())
    whisper_out, deepgram_out = results

    errors: list[str] = []
    if isinstance(whisper_out, BaseException):
        errors.append(f"whisper: {whisper_out}")
        whisper_out = None
    if isinstance(deepgram_out, BaseException):
        errors.append(f"deepgram: {deepgram_out}")
        deepgram_out = None

    if whisper_out is None and deepgram_out is None:
        for err in errors:
            err_console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1)

    if errors:
        for err in errors:
            err_console.print(f"[yellow]Warning:[/yellow] {err}")

    w_result, w_metrics, w_vibe = whisper_out or (None, None, None)
    d_result, d_metrics, d_vibe = deepgram_out or (None, None, None)

    if _state["json_output"]:
        def _pack(result, metrics, vibe):
            if result is None:
                return None
            return {
                "text": result.text,
                "metrics": metrics.model_dump() if metrics else None,
                "vibe": vibe.total if vibe else None,
            }

        _print_json(
            {
                "sample_id": sample_id,
                "reference": sample.reference_text,
                "whisper": _pack(w_result, w_metrics, w_vibe),
                "deepgram": _pack(d_result, d_metrics, d_vibe),
                "errors": errors,
            }
        )
        _maybe_print_math()
        return

    console.print(f"\n[bold]Sample:[/bold] {sample_id} ({sample.condition})")
    console.print(f"[dim]{audio_path}[/dim]\n")
    console.print(f"[bold]Reference[/bold]\n{sample.reference_text}\n")

    table = Table(title="Whisper vs Deepgram")
    table.add_column("Metric")
    table.add_column("Whisper (batch)")
    table.add_column("Deepgram (streaming)")

    def _ttft(m):
        if m is None:
            return "—"
        return f"{m.ttft_ms:.0f}ms" if m.ttft_ms else "—"

    def _m(m, attr, fmt=_fmt_pct):
        if m is None:
            return "—"
        return fmt(getattr(m, attr))

    table.add_row("WER", _m(w_metrics, "wer"), _m(d_metrics, "wer"))
    table.add_row("chrF", _m(w_metrics, "chrf", _fmt_chrf), _m(d_metrics, "chrf", _fmt_chrf))
    table.add_row("Punct F1", _m(w_metrics, "punctuation_f1"), _m(d_metrics, "punctuation_f1"))
    table.add_row("TTFT", _ttft(w_metrics), _ttft(d_metrics))
    table.add_row(
        "Total",
        f"{w_metrics.total_ms:.0f}ms" if w_metrics else "—",
        f"{d_metrics.total_ms:.0f}ms" if d_metrics else "—",
    )
    table.add_row("RTF", _m(w_metrics, "rtf", lambda v: f"{v:.2f}"), _m(d_metrics, "rtf", lambda v: f"{v:.2f}"))
    table.add_row(
        "Cost",
        f"${w_metrics.cost_usd:.4f}" if w_metrics and w_metrics.cost_usd is not None else "—",
        f"${d_metrics.cost_usd:.4f}" if d_metrics and d_metrics.cost_usd is not None else "—",
    )
    table.add_row(
        "Vibe",
        f"{w_vibe.total}" if w_vibe else "—",
        f"{d_vibe.total}" if d_vibe else "—",
    )
    console.print(table)

    console.print("\n[bold]Whisper transcript[/bold]")
    console.print(w_result.text if w_result else "[red]failed[/red]")
    console.print("\n[bold]Deepgram transcript[/bold]")
    console.print(d_result.text if d_result else "[red]failed[/red]")
    _maybe_print_math()


@app.command("listen")
def listen_cmd(
    sample_id: str = typer.Argument(DEFAULT_NOISY_SAMPLE, help="Sample ID — audio plays while transcribing"),
):
    """Play audio (afplay) and compare Whisper vs Deepgram while you listen."""
    import subprocess

    from stt_bench.dataset.loader import get_sample, resolve_audio_path

    settings = get_settings()
    sample = get_sample("default", sample_id, settings)
    audio_path = resolve_audio_path(sample, settings)

    console.print(f"[bold]Playing[/bold] {audio_path}")
    console.print("[dim]Transcription starts immediately — listen and compare.[/dim]\n")
    player = subprocess.Popen(["afplay", str(audio_path)])

    try:
        compare_cmd(sample_id=sample_id, all_samples=False)
    except typer.Exit:
        raise
    except Exception as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        player.wait()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8766, "--port"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Start FastAPI server."""
    import uvicorn

    uvicorn.run(
        "stt_bench.server.app:app",
        host=host,
        port=port,
        reload=reload,
        loop="asyncio",
    )


# --- transcribe ---

transcribe_app = typer.Typer(help="Single-file transcription")
app.add_typer(transcribe_app, name="transcribe")


@transcribe_app.command("file")
def transcribe_file(
    path: Path = typer.Argument(..., help="Audio file path"),
    provider: str = typer.Option("mock", "--provider"),
    mode: str = typer.Option("batch", "--mode"),
    model: Optional[str] = typer.Option(None, "--model"),
    force: bool = typer.Option(False, "--force"),
    local: bool = typer.Option(True, "--local/--api"),
    stream: bool = typer.Option(False, "--stream"),
):
    """Transcribe a single audio file."""
    settings = get_settings()
    provider = _parse_providers([provider])[0]
    prov_model = model or _default_model(provider, settings)
    transport_mode = mode
    if mode == "batch" and _default_mode(provider) == "streaming":
        transport_mode = "streaming"
    config = ProviderConfig(
        provider=provider,  # type: ignore
        model=prov_model,
        transport_mode=transport_mode,  # type: ignore
    )

    if local:
        asyncio.run(_transcribe_local(path, provider, config, force, stream))
        return

    if stream or transport_mode == "streaming":
        _transcribe_stream_api(path, provider, config)
        return

    with _api_client() as client:
        resp = client.post(
            "/api/v1/transcribe",
            json={
                "audio_path": str(path),
                "provider": provider,
                "config": config.model_dump(),
                "force": force,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _print_transcription(data)


async def _transcribe_local(path: Path, provider: str, config: ProviderConfig, force: bool, stream: bool):
    from stt_bench.server.cache import TranscriptionCache
    from stt_bench.server.results.store import ResultsStore
    from stt_bench.server.transcription.service import TranscriptionService

    settings = get_settings()
    store = ResultsStore(settings.db_path)
    await store.init()
    svc = TranscriptionService(settings, TranscriptionCache(store))

    if stream:
        audio = path.read_bytes()
        async for event in svc.transcribe_stream_events(audio, provider, config):
            if event["type"] == "partial":
                p = event["data"]
                console.print(f"[dim]partial:[/dim] {p.text}")
            else:
                _print_transcription(event["data"].model_dump())
        return

    result = await svc.transcribe_path(path, provider, config, force=force)
    _print_transcription(result.model_dump())


def _transcribe_stream_api(path: Path, provider: str, config: ProviderConfig):
    with _api_client() as client:
        with client.stream(
            "POST",
            "/api/v1/transcribe/stream",
            json={
                "audio_path": str(path),
                "provider": provider,
                "config": config.model_dump(),
            },
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    console.print(data)


def _print_transcription(data: dict):
    if _state["json_output"]:
        _print_json(data)
        return
    timings = data.get("timings", {})
    ttft = timings.get("ttft_ms")
    ttft_str = f"{ttft:.0f}ms" if ttft else "—"
    cost = data.get("cost_usd")
    cost_str = f"${cost:.4f}" if cost is not None else "—"
    console.print(
        f"Provider: {data['provider']} ({data['transport_mode']})\n"
        f"Duration: {data['audio_duration_s']:.2f}s | "
        f"Latency: {timings.get('total_ms', 0):.0f}ms | "
        f"RTF: {timings.get('rtf', 0):.2f} | "
        f"TTFT: {ttft_str} | Cost: {cost_str}\n"
        f"{'─' * 56}\n"
        f"[bold]Transcript[/bold]\n"
        f"{data['text'] or '(empty)'}"
    )


def _parse_providers(providers: list[str] | None) -> list[str]:
    """Expand comma-separated and repeated --providers values."""
    if not providers:
        return []
    result: list[str] = []
    for item in providers:
        for part in item.split(","):
            part = part.strip()
            if part:
                result.append(part)
    return result


def _default_model(provider: str, settings) -> str:
    if provider == "whisper":
        return settings.whisper_model
    if provider == "deepgram":
        return settings.deepgram_model
    return "mock-v1"


_PLACEHOLDER_API_KEYS = frozenset({"sk-...", "sk-....", "...", "your-api-key", "changeme"})


def _looks_like_placeholder_api_key(key: str) -> bool:
    stripped = key.strip()
    if stripped in _PLACEHOLDER_API_KEYS:
        return True
    if stripped.endswith("...") and len(stripped) <= 10:
        return True
    return len(stripped) < 20


def _validate_provider_credentials(providers: list[str], settings) -> None:
    """Fail fast when real providers are selected without usable API keys."""
    errors: list[str] = []
    for prov in providers:
        if prov == "mock":
            continue
        if prov == "whisper":
            key = settings.openai_api_key
            env_name = "OPENAI_API_KEY"
        elif prov == "deepgram":
            key = settings.deepgram_api_key
            env_name = "DEEPGRAM_API_KEY"
        else:
            continue

        if not key or not key.strip():
            errors.append(f"{prov}: {env_name} is not set — add it to stt-bench/.env")
        elif _looks_like_placeholder_api_key(key):
            errors.append(
                f"{prov}: {env_name} looks like a placeholder — set a real API key in stt-bench/.env"
            )

    if errors:
        for err in errors:
            err_console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1)


# --- benchmark ---

benchmark_app = typer.Typer(help="Corpus benchmark runs")
app.add_typer(benchmark_app, name="benchmark")


@benchmark_app.command("run")
def benchmark_run(
    dataset: str = typer.Option("default", "--dataset"),
    provider: Optional[str] = typer.Option(None, "--provider"),
    providers: Optional[list[str]] = typer.Option(None, "--providers"),
    mode: Optional[str] = typer.Option(None, "--mode"),
    sample_id: Optional[list[str]] = typer.Option(None, "--sample-id"),
    force: bool = typer.Option(False, "--force"),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    local: bool = typer.Option(True, "--local/--api"),
    verbose: bool = typer.Option(False, "--verbose", help="Print per-sample transcripts"),
):
    """Run benchmark over dataset."""
    prov_list = _parse_providers(providers)
    if not prov_list and provider:
        prov_list = _parse_providers([provider])
    if not prov_list:
        prov_list = ["mock"]
    settings = get_settings()
    _validate_provider_credentials(prov_list, settings)

    any_failed = False
    for prov in prov_list:
        prov_mode = mode or _default_mode(prov)
        prov_model = _default_model(prov, settings)
        config = ProviderConfig(
            provider=prov,  # type: ignore
            model=prov_model,
            transport_mode=prov_mode,  # type: ignore
        )

        if local:
            run = asyncio.run(
                _benchmark_run_local(dataset, prov, prov_mode, config, sample_id, force, wait)
            )
        else:
            run = _benchmark_run_api(dataset, prov, prov_mode, config, sample_id, force, wait)

        if _state["json_output"]:
            _print_json(run)
        elif wait:
            _print_run_summary(run)
            if verbose and run.get("status") == "completed":
                asyncio.run(_print_run_samples(run["id"], run["config"]["dataset_id"]))

        if run.get("status") != "completed":
            any_failed = True

    if any_failed:
        raise typer.Exit(1)


def _default_mode(provider: str) -> str:
    if provider == "deepgram":
        return "streaming"
    return "batch"


async def _benchmark_run_local(
    dataset_id, provider, transport_mode, config, sample_ids, force, wait
):
    from stt_bench.server.benchmark.runner import BenchmarkRunner
    from stt_bench.server.cache import TranscriptionCache
    from stt_bench.server.queue import InProcessQueue
    from stt_bench.server.results.store import ResultsStore

    settings = get_settings()
    store = ResultsStore(settings.db_path)
    await store.init()
    queue = InProcessQueue()
    transcription = __import__(
        "stt_bench.server.transcription.service", fromlist=["TranscriptionService"]
    ).TranscriptionService(settings, TranscriptionCache(store))
    runner = BenchmarkRunner(settings, store, transcription, queue)
    await queue.start()

    run = await runner.create_run(
        dataset_id=dataset_id,
        provider=provider,
        transport_mode=transport_mode,
        provider_config=config,
        sample_ids=sample_ids,
        force=force,
    )

    if wait:
        while True:
            run = await store.get_run(run.id)
            if run and run.status in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.2)
        await queue.stop()
        return run.model_dump()
    await queue.stop()
    return run.model_dump()


def _benchmark_run_api(dataset_id, provider, transport_mode, config, sample_ids, force, wait):
    with _api_client() as client:
        resp = client.post(
            "/api/v1/benchmark/runs",
            json={
                "dataset_id": dataset_id,
                "provider": provider,
                "transport_mode": transport_mode,
                "provider_config": config.model_dump(),
                "sample_ids": sample_ids,
                "force": force,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        run_id = data["id"]

        if wait:
            while True:
                r = client.get(f"/api/v1/benchmark/runs/{run_id}")
                r.raise_for_status()
                run = r.json()
                if run["status"] in ("completed", "failed", "cancelled"):
                    return run
                time.sleep(0.5)
        return data


async def _print_run_samples(run_id: str, dataset_id: str) -> None:
    from stt_bench.dataset.registry import DatasetRegistry
    from stt_bench.server.results.store import ResultsStore

    settings = get_settings()
    store = ResultsStore(settings.db_path)
    await store.init()
    samples = await store.get_sample_results(run_id)
    registry = DatasetRegistry(settings)
    manifest = registry.load(dataset_id)
    refs = {s.id: s.reference_text for s in manifest.samples}

    for s in samples:
        sid = s["sample_id"]
        hyp = (s.get("transcription") or {}).get("text") or s["metrics"].get("hypothesis", "")
        ref = refs.get(sid, "—")
        wer = s["metrics"].get("wer")
        chrf = s["metrics"].get("chrf")
        punct = s["metrics"].get("punctuation_f1")
        console.print(
            f"\n[bold]{sid}[/bold] "
            f"(WER {_fmt_pct(wer)} | chrF {_fmt_chrf(chrf)} | Punct F1 {_fmt_pct(punct)})"
        )
        console.print(f"[dim]Reference:[/dim]  {ref}")
        console.print(f"[dim]Hypothesis:[/dim] {hyp or '(empty)'}")


def _print_run_summary(run: dict):
    agg = run.get("aggregate_metrics") or {}
    status = run["status"]
    vibe = run.get("vibe_score")
    vibe_str = f"{vibe:.1f}" if isinstance(vibe, (int, float)) else "—"
    wer = agg.get("wer_mean")
    chrf = agg.get("chrf_mean")
    punct = agg.get("punctuation_f1_mean")
    console.print(
        f"\n[bold]Run {run['id']}[/bold] — {run['config']['provider']} "
        f"({run['config']['transport_mode']})\n"
        f"Status: {status} | Samples: {run['sample_count']} | "
        f"Vibe: {vibe_str} | WER: {_fmt_pct(wer)} | "
        f"chrF: {_fmt_chrf(chrf)} | Punct F1: {_fmt_pct(punct)}"
    )
    if status == "failed" and run.get("error"):
        err_console.print(f"[red]Error:[/red] {run['error']}")
    elif status == "cancelled":
        err_console.print("[yellow]Run was cancelled[/yellow]")


@benchmark_app.command("status")
def benchmark_status(run_id: str = typer.Argument(...)):
    """Check benchmark run status."""
    with _api_client() as client:
        resp = client.get(f"/api/v1/benchmark/runs/{run_id}")
        resp.raise_for_status()
        data = resp.json()
        if _state["json_output"]:
            _print_json(data)
        else:
            _print_run_summary(data)


@benchmark_app.command("list")
def benchmark_list(limit: int = typer.Option(20, "--limit")):
    """List benchmark runs."""
    settings = get_settings()

    async def _local_list():
        from stt_bench.server.results.store import ResultsStore

        store = ResultsStore(settings.db_path)
        await store.init()
        return [r.model_dump() for r in await store.list_runs(limit=limit)]

    try:
        with _api_client() as client:
            resp = client.get("/api/v1/benchmark/runs", params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()["runs"]
    except (httpx.ConnectError, httpx.HTTPStatusError):
        data = asyncio.run(_local_list())

    if _state["json_output"]:
        _print_json(data)
        return

    table = Table(title="Benchmark Runs")
    table.add_column("ID")
    table.add_column("Provider")
    table.add_column("Status")
    table.add_column("Vibe")
    for r in data:
        table.add_row(
            r["id"],
            r["config"]["provider"],
            r["status"],
            str(r.get("vibe_score", "—")),
        )
    console.print(table)


# --- dataset ---

dataset_app = typer.Typer(help="Dataset management")
app.add_typer(dataset_app, name="dataset")


@dataset_app.command("list")
def dataset_list():
    """List available datasets."""
    from stt_bench.dataset.loader import list_datasets

    data = list_datasets()
    if _state["json_output"]:
        _print_json(data)
        return
    for ds in data:
        console.print(f"{ds['dataset_id']}: {ds['name']} ({ds['sample_count']} samples)")


@dataset_app.command("show")
def dataset_show(dataset_id: str = typer.Argument("default")):
    """Show dataset details."""
    from stt_bench.dataset.loader import get_dataset_stats

    stats = get_dataset_stats(dataset_id=dataset_id)
    if _state["json_output"]:
        _print_json(stats)
        return
    console.print(f"[bold]{stats['name']}[/bold] ({stats['dataset_id']})")
    console.print(f"Samples: {stats['sample_count']}")
    console.print(f"Conditions: {stats['conditions']}")
    console.print(f"Est. duration: {stats['estimated_total_duration_s']}s")


@dataset_app.command("info")
def dataset_info(dataset_id: str = typer.Argument("default")):
    """Alias for dataset show."""
    dataset_show(dataset_id)


@dataset_app.command("validate")
def dataset_validate(dataset_id: str = typer.Option("default", "--dataset")):
    """Validate dataset manifest and audio paths."""
    from stt_bench.dataset.loader import validate_dataset

    result = validate_dataset(dataset_id=dataset_id)
    if _state["json_output"]:
        _print_json(result)
        return
    if result["valid"]:
        console.print(f"[green]✓[/green] Dataset '{result['dataset_id']}' valid ({result['sample_count']} samples)")
    else:
        console.print(f"[red]✗[/red] Validation failed:")
        for err in result["errors"]:
            console.print(f"  - {err}")
        raise typer.Exit(1)


@dataset_app.command("stats")
def dataset_stats_cmd(dataset_id: str = typer.Argument("default")):
    """Dataset statistics."""
    dataset_show(dataset_id)


# --- results ---

results_app = typer.Typer(help="Results and leaderboard")
app.add_typer(results_app, name="results")


@results_app.command("leaderboard")
def results_leaderboard(
    dataset: str = typer.Option("default", "--dataset"),
    top: int = typer.Option(10, "--top"),
    limit: int = typer.Option(None, "--limit"),
    exclude_mock: bool = typer.Option(False, "--exclude-mock", help="Hide mock provider runs"),
):
    """Show ranked benchmark results."""
    n = limit or top
    settings = get_settings()

    async def _local():
        from stt_bench.server.results.store import ResultsStore

        store = ResultsStore(settings.db_path)
        await store.init()
        entries = await store.leaderboard(dataset_id=dataset, limit=n, exclude_mock=exclude_mock)
        return [e.model_dump() for e in entries]

    try:
        with _api_client() as client:
            params: dict = {"dataset_id": dataset, "limit": n}
            if exclude_mock:
                params["exclude_mock"] = True
            resp = client.get("/api/v1/results/leaderboard", params=params)
            resp.raise_for_status()
            entries = resp.json()["entries"]
    except (httpx.ConnectError, httpx.HTTPStatusError):
        entries = asyncio.run(_local())

    if exclude_mock:
        entries = [e for e in entries if e.get("provider") != "mock"]

    if _state["json_output"]:
        _print_json(entries)
        return

    table = Table(title=f"STT Bench Leaderboard — dataset: {dataset}")
    table.add_column("Rank")
    table.add_column("Provider")
    table.add_column("Mode")
    table.add_column("Vibe")
    table.add_column("WER")
    table.add_column("chrF")
    table.add_column("TTFT p50")
    table.add_column("Cost")
    for e in entries:
        ttft = e.get("ttft_p50_ms")
        table.add_row(
            str(e["rank"]),
            e["provider"],
            e["transport_mode"],
            f"{e['vibe_score']:.1f}",
            _fmt_pct(e.get("wer_mean")),
            _fmt_chrf(e.get("chrf_mean")),
            f"{ttft:.0f}ms" if ttft else "—",
            f"${e['cost_total_usd']:.4f}",
        )
    console.print(table)


@results_app.command("list")
def results_list(limit: int = typer.Option(20, "--limit")):
    """List completed runs."""
    benchmark_list(limit=limit)


@results_app.command("show")
def results_show(run_id: str = typer.Argument(...)):
    """Show run details."""
    settings = get_settings()

    async def _local():
        from stt_bench.server.results.store import ResultsStore

        store = ResultsStore(settings.db_path)
        await store.init()
        run = await store.get_run(run_id)
        if not run:
            raise typer.Exit(1)
        samples = await store.get_sample_results(run_id)
        return {"run": run.model_dump(), "samples": samples}

    try:
        with _api_client() as client:
            r = client.get(f"/api/v1/benchmark/runs/{run_id}")
            r.raise_for_status()
            s = client.get(f"/api/v1/benchmark/runs/{run_id}/samples")
            s.raise_for_status()
            data = {"run": r.json(), "samples": s.json()["samples"]}
    except (httpx.ConnectError, httpx.HTTPStatusError):
        data = asyncio.run(_local())

    if _state["json_output"]:
        _print_json(data)
    else:
        _print_run_summary(data["run"])
        asyncio.run(_print_run_samples(run_id, data["run"]["config"]["dataset_id"]))


@results_app.command("export")
def results_export(run_id: str = typer.Argument(...), out: Path = typer.Argument(...)):
    """Export run to JSONL."""
    with _api_client() as client:
        resp = client.get(f"/api/v1/results/runs/{run_id}/export")
        resp.raise_for_status()
        content = resp.json()["content"]
        out.write_text(content)
        console.print(f"Exported to {out}")


@results_app.command("import")
def results_import(path: Path = typer.Argument(...)):
    """Import run from JSONL."""
    with _api_client() as client:
        with open(path, "rb") as f:
            resp = client.post("/api/v1/results/import", files={"file": f})
        resp.raise_for_status()
        console.print("Import complete")


# --- provider ---

provider_app = typer.Typer(help="Provider management")
app.add_typer(provider_app, name="provider")


@provider_app.command("list")
def provider_list(local: bool = typer.Option(True, "--local/--api")):
    """List STT providers."""
    if local:
        from stt_bench.providers.base import list_providers

        providers = list_providers(get_settings())
        data = [
            {
                "name": p.name,
                "display_name": p.display_name,
                "capabilities": p.capabilities.model_dump(),
            }
            for p in providers
        ]
    else:
        with _api_client() as client:
            resp = client.get("/api/v1/providers")
            resp.raise_for_status()
            data = resp.json()["providers"]

    if _state["json_output"]:
        _print_json(data)
        return
    for p in data:
        caps = p["capabilities"]
        modes = []
        if caps.get("supports_batch"):
            modes.append("batch")
        if caps.get("supports_streaming"):
            modes.append("streaming")
        console.print(f"{p['name']}: {p['display_name']} [{', '.join(modes)}]")


@provider_app.command("validate")
def provider_validate(name: str = typer.Argument(...)):
    """Validate provider API key."""
    with _api_client() as client:
        resp = client.post(
            f"/api/v1/providers/{name}/validate",
            json={"config": {"provider": name, "model": _default_model(name, get_settings())}},
        )
        if resp.status_code >= 400:
            console.print(f"[red]Invalid:[/red] {resp.json()}")
            raise typer.Exit(1)
        console.print(f"[green]✓[/green] {resp.json()['message']}")


@provider_app.command("test")
def provider_test(
    name: str = typer.Argument(...),
    audio: Path = typer.Argument(...),
    local: bool = typer.Option(True, "--local/--api"),
):
    """Quick smoke test on one audio file."""
    mode = _default_mode(name)
    transcribe_file(
        path=audio,
        provider=name,
        mode=mode,
        model=None,
        force=True,
        local=local,
        stream=mode == "streaming",
    )


if __name__ == "__main__":
    app()
