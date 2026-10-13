"""Render docs/assets/demo-mock-bench.gif from a real mock ``stt-bench`` run.

The GIF types the three quick-start commands and shows their TTY output
(benchmark summary, a snippet of the markdown report, and the leaderboard).
Numbers come from the CLI; nothing in the frame is hand-written metrics.

Regen (from the repo root, with ``stt-bench`` on ``PATH``)::

    pip install pyte pillow
    python docs/assets/render_demo_gif.py

Needs a monospace TTF with box drawing (JetBrains Mono or DejaVu Sans Mono)
and the ``stt-bench`` console script. ffmpeg is not required.
"""

from __future__ import annotations

import fcntl
import math
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
from dataclasses import dataclass
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "demo-mock-bench.gif"

COLS = 102
ROWS = 48
VISIBLE = 22
FONT_SIZE = 15

# Catppuccin Mocha. Flat fills keep the GIF small.
BG = (30, 30, 46)
MANTLE = (24, 24, 37)
CRUST = (17, 17, 27)
SURFACE = (49, 50, 68)
FG = (205, 214, 244)
GREEN = (166, 227, 161)
CURSOR = (137, 180, 250)

ANSI = {
    "black": (69, 71, 90),
    "red": (243, 139, 168),
    "green": (166, 227, 161),
    "yellow": (249, 226, 175),
    "blue": (137, 180, 250),
    "magenta": (203, 166, 247),
    "cyan": (137, 220, 235),
    "white": (205, 214, 244),
    "brightblack": (108, 112, 134),
    "brightred": (243, 139, 168),
    "brightgreen": (166, 227, 161),
    "brightyellow": (249, 226, 175),
    "brightblue": (137, 180, 250),
    "brightmagenta": (203, 166, 247),
    "brightcyan": (137, 220, 235),
    "brightwhite": (255, 255, 255),
    "default": FG,
}

COMMANDS = (
    "stt-bench benchmark run --provider mock --force",
    "stt-bench report --format markdown",
    "stt-bench results leaderboard",
)


@dataclass(frozen=True)
class Cell:
    ch: str = " "
    fg: tuple[int, int, int] = FG
    bold: bool = False
    italic: bool = False


def _font(*names: str) -> ImageFont.FreeTypeFont:
    for name in names:
        if Path(name).is_file():
            return ImageFont.truetype(name, FONT_SIZE)
    sys.exit("No monospace font found (JetBrains Mono or DejaVu Sans Mono).")


def load_fonts() -> dict[str, ImageFont.FreeTypeFont]:
    jb = "/usr/share/fonts/truetype/jetbrains-mono"
    dj = "/usr/share/fonts/truetype/dejavu"
    regular = _font(f"{jb}/JetBrainsMono-Regular.ttf", f"{dj}/DejaVuSansMono.ttf")
    bold = _font(f"{jb}/JetBrainsMono-Bold.ttf", f"{dj}/DejaVuSansMono-Bold.ttf")
    italic = _font(f"{jb}/JetBrainsMono-Italic.ttf", f"{dj}/DejaVuSansMono-Oblique.ttf")
    return {"regular": regular, "bold": bold, "italic": italic}


def capture(cmd: list[str], env: dict[str, str], timeout: float = 180) -> bytes:
    master, slave = pty.openpty()
    winsize = struct.pack("HHHH", ROWS, COLS, 0, 0)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, winsize)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
    )
    os.close(slave)
    chunks: list[bytes] = []
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.3)
            if ready:
                try:
                    block = os.read(master, 65536)
                except OSError:
                    break
                if not block:
                    break
                chunks.append(block)
            elif proc.poll() is not None:
                while True:
                    ready, _, _ = select.select([master], [], [], 0.05)
                    if not ready:
                        break
                    try:
                        block = os.read(master, 65536)
                    except OSError:
                        block = b""
                    if not block:
                        break
                    chunks.append(block)
                break
        else:
            proc.kill()
            raise SystemExit(f"timed out: {' '.join(cmd)}")
    finally:
        os.close(master)
    rc = proc.wait()
    data = b"".join(chunks)
    if rc != 0:
        sys.stderr.write(data.decode("utf-8", "replace"))
        raise SystemExit(f"{' '.join(cmd)} exited {rc}")
    return data


def paint(screen: pyte.Screen) -> list[list[Cell]]:
    rows: list[list[Cell]] = []
    for y in range(screen.lines):
        row: list[Cell] = []
        for x in range(screen.columns):
            ch = screen.buffer[y][x]
            color = ANSI.get(ch.fg, FG)
            row.append(Cell(ch.data or " ", color, bool(ch.bold), bool(ch.italics)))
        rows.append(row)
    while rows and _blank(rows[0]):
        rows.pop(0)
    while rows and _blank(rows[-1]):
        rows.pop()
    return rows


def _blank(row: list[Cell]) -> bool:
    return all(cell.ch == " " for cell in row)


def _text(row: list[Cell]) -> str:
    return "".join(cell.ch for cell in row).rstrip()


def report_snippet(rows: list[list[Cell]]) -> list[list[Cell]]:
    """Header, metrics table, and the first note. Later notes are long and wrap."""
    kept: list[list[Cell]] = []
    for row in rows:
        kept.append(row)
        if _text(row).startswith("- Mock provider"):
            break
    return kept


def run_cli(db_path: Path) -> tuple[list[list[list[Cell]]], str]:
    binary = shutil.which("stt-bench")
    if not binary:
        raise SystemExit("stt-bench is not on PATH. pip install -e .  and retry.")
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["FORCE_COLOR"] = "1"
    env["COLUMNS"] = str(COLS)
    env["LINES"] = str(ROWS)
    env["STT_BENCH_DB_PATH"] = str(db_path)
    env.pop("NO_COLOR", None)

    invocations = [
        [binary, "benchmark", "run", "--provider", "mock", "--force"],
        [binary, "report", "--format", "markdown"],
        [binary, "results", "leaderboard"],
    ]
    screens: list[list[list[Cell]]] = []
    for cmd in invocations:
        raw = capture(cmd, env)
        screen = pyte.Screen(COLS, ROWS)
        pyte.Stream(screen).feed(raw.decode("utf-8", "replace"))
        screens.append(paint(screen))

    report_path = db_path.with_name("report.md")
    capture(
        [binary, "report", "--format", "markdown", "--out", str(report_path)],
        env,
    )
    report_text = report_path.read_text(encoding="utf-8")
    screens[1] = report_snippet(screens[1])
    _check_output(screens, report_text)
    return screens, report_text


def _check_output(screens: list[list[list[Cell]]], report_text: str) -> None:
    bench = "\n".join(_text(row) for row in screens[0])
    board = "\n".join(_text(row) for row in screens[2])
    if "Status: completed" not in bench or "mock" not in bench:
        raise SystemExit("benchmark output did not look like a completed mock run")
    if "STT Bench Leaderboard" not in board or "┃" not in board:
        raise SystemExit("leaderboard output did not render a table")
    if "| mock |" not in report_text or "WER" not in report_text:
        raise SystemExit("markdown report did not contain the mock row")


def blank_row() -> list[Cell]:
    return [Cell() for _ in range(COLS)]


def prompt_row(typed: str) -> list[Cell]:
    row = blank_row()
    row[0] = Cell("$", GREEN, bold=True)
    row[1] = Cell(" ")
    for index, ch in enumerate(typed):
        col = index + 2
        if col >= COLS:
            break
        row[col] = Cell(ch, FG)
    return row


class Session:
    def __init__(self) -> None:
        self.lines: list[list[Cell]] = []
        self.cursor: tuple[int, int] | None = None

    def start_prompt(self) -> None:
        self.lines.append(prompt_row(""))
        self.cursor = (len(self.lines) - 1, 2)

    def set_typed(self, typed: str) -> None:
        self.lines[-1] = prompt_row(typed)
        self.cursor = (len(self.lines) - 1, min(2 + len(typed), COLS - 1))

    def newline(self) -> None:
        self.lines.append(blank_row())
        self.cursor = None

    def add_output(self, row: list[Cell]) -> None:
        self.lines.append(row)
        self.cursor = None


def viewport(lines: list[list[Cell]]) -> list[list[Cell]]:
    if len(lines) <= VISIBLE:
        return lines + [blank_row() for _ in range(VISIBLE - len(lines))]
    return lines[-VISIBLE:]


def render_frame(
    lines: list[list[Cell]],
    cursor: tuple[int, int] | None,
    fonts: dict[str, ImageFont.FreeTypeFont],
    cell_w: int,
    cell_h: int,
) -> Image.Image:
    margin = 16
    pad_x = 16
    pad_y = 12
    title_h = 36
    term_w = pad_x * 2 + COLS * cell_w
    term_h = title_h + pad_y * 2 + VISIBLE * cell_h
    image = Image.new("RGB", (term_w + margin * 2, term_h + margin * 2), CRUST)
    draw = ImageDraw.Draw(image)
    origin = (margin, margin)
    draw.rounded_rectangle(
        [origin, (origin[0] + term_w - 1, origin[1] + term_h - 1)],
        radius=12,
        fill=BG,
    )
    draw.rounded_rectangle(
        [origin, (origin[0] + term_w - 1, origin[1] + title_h)],
        radius=12,
        fill=MANTLE,
    )
    # Square off the bottom of the title bar so only the window's top is rounded.
    draw.rectangle(
        [origin[0], origin[1] + title_h - 12, origin[0] + term_w - 1, origin[1] + title_h],
        fill=MANTLE,
    )
    draw.line(
        [(origin[0], origin[1] + title_h), (origin[0] + term_w - 1, origin[1] + title_h)],
        fill=SURFACE,
    )
    for index, color in enumerate(((243, 139, 168), (249, 226, 175), (166, 227, 161))):
        cx = origin[0] + 18 + index * 18
        cy = origin[1] + title_h // 2
        draw.ellipse([cx, cy - 5, cx + 10, cy + 5], fill=color)
    title = "stt-bench  ·  mock"
    title_font = fonts["regular"]
    title_w = title_font.getlength(title)
    draw.text(
        (origin[0] + (term_w - title_w) / 2, origin[1] + 9),
        title,
        font=title_font,
        fill=(147, 153, 178),
    )

    view = viewport(lines)
    offset = max(0, len(lines) - VISIBLE)
    text_x = origin[0] + pad_x
    text_y = origin[1] + title_h + pad_y
    for row_index, row in enumerate(view):
        for col_index, cell in enumerate(row):
            if cell.ch == " ":
                continue
            font = fonts["bold"] if cell.bold else fonts["italic"] if cell.italic else fonts["regular"]
            draw.text(
                (text_x + col_index * cell_w, text_y + row_index * cell_h),
                cell.ch,
                font=font,
                fill=cell.fg,
            )
    if cursor is not None:
        row_index = cursor[0] - offset
        if 0 <= row_index < VISIBLE:
            x = text_x + cursor[1] * cell_w
            y = text_y + row_index * cell_h + 1
            draw.rectangle([x, y, x + cell_w - 2, y + cell_h - 4], fill=CURSOR)
    return image


def build_frames(
    outputs: list[list[list[Cell]]],
    fonts: dict[str, ImageFont.FreeTypeFont],
    cell_w: int,
    cell_h: int,
) -> list[tuple[Image.Image, int]]:
    session = Session()
    frames: list[tuple[Image.Image, int]] = []

    def snap(ms: int) -> None:
        frames.append((render_frame(session.lines, session.cursor, fonts, cell_w, cell_h), ms))

    session.start_prompt()
    snap(280)
    for index, (command, output) in enumerate(zip(COMMANDS, outputs, strict=True)):
        typed = ""
        for step in range(0, len(command), 2):
            typed = command[: step + 2]
            session.set_typed(typed)
            snap(55)
        session.set_typed(command)
        snap(280)
        session.newline()
        for row in output:
            session.add_output(row)
            snap(70)
        if index != len(COMMANDS) - 1:
            session.newline()
            session.start_prompt()
            snap(220)
    session.cursor = None
    snap(1600)
    return frames


def quantize(frames: list[Image.Image]) -> list[Image.Image]:
    picks = frames[:: max(1, len(frames) // 8)][:8]
    width, height = picks[0].size
    sheet = Image.new("RGB", (width, height * len(picks)))
    for index, frame in enumerate(picks):
        sheet.paste(frame, (0, index * height))
    palette = sheet.quantize(colors=64, dither=Image.Dither.NONE, method=Image.Quantize.MEDIANCUT)
    return [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]


def cell_size(font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    width = math.ceil(font.getlength("0" * 40) / 40)
    ascent, descent = font.getmetrics()
    return width, ascent + descent + 3


def main() -> None:
    fonts = load_fonts()
    cell_w, cell_h = cell_size(fonts["regular"])
    with tempfile.TemporaryDirectory(prefix="stt-bench-demo-") as tmp:
        db_path = Path(tmp) / "results.db"
        outputs, _report_text = run_cli(db_path)
    frames = build_frames(outputs, fonts, cell_w, cell_h)
    hero = frames[-1][0]
    # First frame is the finished screen so a client that does not animate
    # still shows the report snippet and the leaderboard.
    ordered = [(hero, 900)] + frames[:-1] + [(hero, 1800)]
    images = quantize([frame for frame, _duration in ordered])
    durations = [duration for _frame, duration in ordered]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        OUT,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=2,
    )
    size = OUT.stat().st_size
    print(f"wrote {OUT} ({size} bytes, {len(images)} frames, {cell_w}x{cell_h} cells)")
    if size > 3_000_000:
        raise SystemExit(f"GIF is {size} bytes; keep it under 3 MB")


if __name__ == "__main__":
    main()
