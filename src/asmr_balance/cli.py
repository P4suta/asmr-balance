"""Typer CLI surface — thin shell over :mod:`asmr_balance.scan`.

Commands:

* ``asmr-balance scan PATH`` — recursively analyse audio/video files under
  ``PATH`` and write Parquet (+ optional HTML / TUI summary).
* ``asmr-balance inspect FILE`` — analyse one file and print a Rich panel.
* ``asmr-balance schema`` — emit the canonical parquet column list.
* ``asmr-balance version`` — print the package version.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final

import typer
from rich.console import Console

from asmr_balance import __version__
from asmr_balance.config.model import Config
from asmr_balance.config.toml import load_config
from asmr_balance.logging import configure_logging, get_logger
from asmr_balance.scan.parallel import scan_many
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.sink.base import COLUMN_NAMES, build_sinks
from asmr_balance.sink.tui import render_inspect
from asmr_balance.source.adt import LayoutPolicy

if TYPE_CHECKING:
    pass


_AUDIO_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".wav", ".flac", ".ogg", ".opus", ".aiff", ".aif", ".au",
        ".mp4", ".mkv", ".webm", ".m4a", ".mov", ".mp3", ".aac",
    }
)

app = typer.Typer(
    name="asmr-balance",
    help="Multi-axis L/R balance scanner for ASMR audio (ITU-R BS.1770).",
    no_args_is_help=True,
    add_completion=False,
)
_log = get_logger(__name__)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def _global_options(
    log_level: Annotated[str, typer.Option(help="DEBUG/INFO/WARNING/ERROR")] = "INFO",
    log_json: Annotated[bool, typer.Option("--log-json", help="Force JSON log output")] = False,
    version: Annotated[
        bool, typer.Option("--version", "-V", callback=_version_callback, is_eager=True)
    ] = False,
) -> None:
    _ = version
    configure_logging(level=log_level, json=log_json)


def _find_audio_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _AUDIO_EXTENSIONS)


def _resolve_config(
    config_file: Path | None,
    gate: float | None,
    layout_policy: LayoutPolicy | None,
    workers: int | None,
) -> Config:
    base = load_config(config_file) if config_file is not None else Config()
    return base.with_overrides(gate_lufs=gate, layout_policy=layout_policy, workers=workers)


@app.command()
def scan(
    path: Annotated[Path, typer.Argument(exists=True, help="Directory or file to scan.")],
    out: Annotated[Path, typer.Option("--out", "-o")] = Path("./report.parquet"),
    html: Annotated[Path | None, typer.Option("--html")] = None,
    config_file: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    gate: Annotated[float | None, typer.Option("--gate", help="Absolute gate (LUFS)")] = None,
    layout: Annotated[
        LayoutPolicy | None, typer.Option("--layout", help="Layout policy for non-stereo audio")
    ] = None,
    workers: Annotated[
        int | None, typer.Option("--workers", help="Worker process count (0=auto)")
    ] = None,
    summary: Annotated[bool, typer.Option("--summary/--no-summary")] = True,
) -> None:
    """Recursively analyse files under ``PATH`` and write the report."""
    config = _resolve_config(config_file, gate, layout, workers)
    files = _find_audio_files(path)
    _log.info("scan_start", root=str(path), file_count=len(files), workers=config.workers)
    if not files:
        typer.echo(f"no audio files found under {path}")
        raise typer.Exit(code=1)
    sinks = build_sinks(out_parquet=[str(out)], out_html=str(html) if html else None, show_summary=summary)
    for sink in sinks:
        sink.open()
    written = 0
    try:
        for result in scan_many(files, config):
            for sink in sinks:
                sink.write(result)
            written += 1
            _log.info(
                "scanned",
                file=str(result.record.meta.file_path),
                verdict=result.verdict.name,
                flag_count=len(result.flags),
                elapsed_sec=result.elapsed_sec,
            )
    finally:
        for sink in sinks:
            sink.close()
    _log.info("scan_done", file_count=written, parquet=str(out))


@app.command()
def inspect(
    file: Annotated[Path, typer.Argument(exists=True, help="One file to analyse")],
    config_file: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    gate: Annotated[float | None, typer.Option("--gate")] = None,
    layout: Annotated[LayoutPolicy | None, typer.Option("--layout")] = None,
) -> None:
    """Analyse a single file and pretty-print its metrics + flags."""
    config = _resolve_config(config_file, gate, layout, workers=1)
    result = scan_one(file, config)
    render_inspect(result, console=Console())


@app.command()
def schema(
    out_format: Annotated[str, typer.Option("--format", help="json | plain")] = "plain",
) -> None:
    """Emit the canonical parquet column list (debug helper)."""
    if out_format == "json":
        typer.echo(json.dumps(list(COLUMN_NAMES), ensure_ascii=False, indent=2))
    else:
        for name in COLUMN_NAMES:
            typer.echo(name)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
