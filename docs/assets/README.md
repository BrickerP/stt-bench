# Demo asset

`demo-mock-bench.gif` is the README recording of a mock run. It types:

```bash
stt-bench benchmark run --provider mock --force
stt-bench report --format markdown
stt-bench results leaderboard
```

Numbers and table text are the CLI's TTY output for that run. The report section is a snippet: title, metrics table, and the first note. Later notes wrap and are left out of the clip. The leaderboard is the full table. The plain report from the same run is `reports/examples/mock-report.md`.

Regenerate from the repo root (`stt-bench` on `PATH`):

```bash
pip install -e ".[dev]" pyte pillow
python docs/assets/render_demo_gif.py
```

The script opens a 102-column terminal, runs the three commands against a temporary SQLite file, and overwrites `demo-mock-bench.gif`. No API keys. Needs JetBrains Mono or DejaVu Sans Mono.
