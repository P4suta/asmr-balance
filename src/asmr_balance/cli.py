"""Typer CLI entry-point for asmr-balance.

Subcommands:

- ``scan``     — recursively scan a directory (or single file) → Parquet
- ``inspect``  — Phase E; placeholder for now
- ``schema``   — Phase E; placeholder for now
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from asmr_balance import __version__
from asmr_balance.config import Config, LayoutPolicy
from asmr_balance.logging import configure_logging, get_logger
from asmr_balance.pipeline import find_audio_files, scan_many, scan_one
from asmr_balance.report.html import write_html
from asmr_balance.report.tui import render_inspect, render_summary
from asmr_balance.report.writer import write_parquet
from asmr_balance.types import MetricRecord

app = typer.Typer(
    name="asmr-balance",
    help="Multi-axis L/R balance scanner for ASMR audio/video files.",
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"asmr-balance {__version__}")
        raise typer.Exit


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="DEBUG | INFO | WARNING | ERROR"),
    ] = "INFO",
    log_json: Annotated[
        bool,
        typer.Option("--log-json", help="Force JSON log output (default: TTY detection)."),
    ] = False,
) -> None:
    """Configure logging before any subcommand runs."""
    configure_logging(level=log_level, json=log_json)


@app.command()
def scan(
    path: Annotated[
        Path,
        typer.Argument(exists=True, readable=True, help="File or directory to scan."),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Parquet output path."),
    ] = Path("./report.parquet"),
    html_out: Annotated[
        Path | None,
        typer.Option("--html", help="Optional HTML report path."),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", exists=True, readable=True),
    ] = None,
    gate: Annotated[
        float | None,
        typer.Option("--gate", help="Absolute gate in LUFS."),
    ] = None,
    layout_policy: Annotated[
        LayoutPolicy | None,
        typer.Option("--layout-policy", help="Multichannel handling."),
    ] = None,
    summary: Annotated[
        bool,
        typer.Option("--summary/--no-summary", help="Print Rich summary table."),
    ] = True,
) -> None:
    """Recursively scan ``PATH`` and write Parquet + (optional) HTML reports."""
    log = get_logger(__name__)
    config = _resolve_config(config_file, gate=gate, layout_policy=layout_policy)
    files = find_audio_files(path)
    log.info("scan_start", root=str(path), file_count=len(files))
    results = scan_many(files, config)
    written = write_parquet(results, out)
    log.info("scan_done", file_count=len(results), parquet=str(out), rows=written)
    if html_out is not None:
        html_rows = write_html(results, html_out)
        log.info("html_written", path=str(html_out), rows=html_rows)
    if summary:
        render_summary(results)
    typer.echo(f"Wrote {written} rows to {out}")


@app.command()
def inspect(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", exists=True, readable=True),
    ] = None,
    gate: Annotated[float | None, typer.Option("--gate")] = None,
    layout_policy: Annotated[
        LayoutPolicy | None,
        typer.Option("--layout-policy"),
    ] = None,
) -> None:
    """Render a verbose Rich panel for a single audio/video file."""
    config = _resolve_config(config_file, gate=gate, layout_policy=layout_policy)
    result = scan_one(path, config)
    render_inspect(result)


@app.command()
def schema() -> None:
    """Print the Parquet column schema as JSON to stdout."""
    column_types: dict[str, str] = {
        name: _python_type_name(field) for name, field in MetricRecord.model_fields.items()
    }
    column_types["flags"] = "list[str]"
    column_types["verdict"] = "str"
    typer.echo(json.dumps(column_types, indent=2, sort_keys=True))


def _resolve_config(
    config_file: Path | None,
    *,
    gate: float | None,
    layout_policy: LayoutPolicy | None,
) -> Config:
    base = Config.from_toml(config_file) if config_file is not None else Config()
    overrides: dict[str, object] = {}
    if gate is not None:
        overrides["gate_lufs"] = gate
    if layout_policy is not None:
        overrides["layout_policy"] = layout_policy
    return base.model_copy(update=overrides) if overrides else base


def _python_type_name(field: object) -> str:
    annotation = getattr(field, "annotation", None)
    if annotation is None:
        return "unknown"
    return str(annotation).replace("typing.", "")
