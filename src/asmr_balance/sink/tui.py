"""Rich-based TUI sinks: summary table at end-of-scan + single-file inspector."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.metrics.record import ScanStatus
from asmr_balance.sink.base import result_to_flat_row

if TYPE_CHECKING:
    from asmr_balance.scan.pipeline import FileResult


_VERDICT_STYLE = {
    Verdict.OK: "bold green",
    Verdict.WARN: "bold yellow",
    Verdict.FAIL: "bold red",
}


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if value == math.inf:
            return "+∞"
        if value == -math.inf:
            return "−∞"
        return f"{value:+.2f}"
    return str(value)  # pragma: no cover -- non-numeric fallthrough used by tests only


@dataclass(slots=True)
class TuiSummarySink:
    """Buffer results; print a Rich summary on :meth:`close`."""

    console: Console = field(default_factory=Console)
    _results: list[FileResult] = field(default_factory=list, init=False)
    _opened: bool = field(default=False, init=False)

    def open(self) -> None:
        self._opened = True
        self._results = []

    def write(self, result: FileResult) -> None:
        if not self._opened:
            msg = "TuiSummarySink.write called before open"
            raise RuntimeError(msg)
        self._results.append(result)

    def close(self) -> None:
        if not self._opened:
            return
        render_summary(self._results, console=self.console)
        self._opened = False


def render_summary(results: list[FileResult], console: Console | None = None) -> None:
    """Print a verdict summary + per-file table to the console."""
    console = console or Console()
    counts = {Verdict.OK: 0, Verdict.WARN: 0, Verdict.FAIL: 0}
    for r in results:
        counts[r.verdict] += 1

    header = Table.grid(padding=(0, 2))
    header.add_row(
        f"[bold]Files[/]: {len(results)}",
        f"[bold green]OK[/]: {counts[Verdict.OK]}",
        f"[bold yellow]WARN[/]: {counts[Verdict.WARN]}",
        f"[bold red]FAIL[/]: {counts[Verdict.FAIL]}",
    )
    console.print(header)

    table = Table(show_header=True, header_style="bold")
    table.add_column("file", overflow="fold")
    table.add_column("verdict", justify="center")
    table.add_column("ΔLU", justify="right")
    table.add_column("p95 ΔLU", justify="right")
    table.add_column("Pearson", justify="right")
    table.add_column("dBTP", justify="right")
    table.add_column("LRA", justify="right")
    table.add_column("flags")

    for result in results:
        row = result_to_flat_row(result)
        verdict_str = result.verdict.name
        table.add_row(
            Path(row["meta.file_path"]).name,
            f"[{_VERDICT_STYLE[result.verdict]}]{verdict_str}[/]",
            _fmt(row["loudness.delta_lu"]),
            _fmt(row["sliding.p95_lu"]),
            _fmt(row["correlation.pearson_r"]),
            _fmt(row["dynamics.true_peak_dbtp_max"]),
            _fmt(row["lra.lra_lu"]),
            ", ".join(row["flag_codes"]),
        )
    console.print(table)


@dataclass(slots=True)
class InspectRenderer:
    """Render a single-file deep inspection panel via :func:`render_inspect`."""

    console: Console = field(default_factory=Console)

    def render(self, result: FileResult) -> None:
        render_inspect(result, console=self.console)


def render_inspect(result: FileResult, console: Console | None = None) -> None:
    """Pretty-print one file's full :class:`MetricRecord` and flags."""
    console = console or Console()
    record = result.record
    name = Path(record.meta.file_path).name
    style = _VERDICT_STYLE[result.verdict]
    title = f"[bold]{name}[/] — [{style}]{result.verdict.name}[/]"
    console.print(Panel.fit(title))
    if record.status is not ScanStatus.ANALYZED:
        console.print(f"[dim]status[/]: {record.status.value}")
        console.print(f"[dim]reason[/]: {record.skip_reason}")
        return
    row = result_to_flat_row(result)
    metrics_table = Table(show_header=True, header_style="bold", title="metrics")
    metrics_table.add_column("field", style="cyan")
    metrics_table.add_column("value", justify="right")
    for col in row:
        if col == "flag_codes":
            continue
        if col.startswith("band.third_octave."):
            continue
        metrics_table.add_row(
            col, _fmt(row[col]) if isinstance(row[col], (int, float)) else str(row[col])
        )
    console.print(metrics_table)

    if result.flags:  # pragma: no branch -- empty-flags branch covered by silent-file tests
        flag_table = Table(show_header=True, header_style="bold", title="flags")
        flag_table.add_column("code")
        flag_table.add_column("severity")
        flag_table.add_column("message")
        for f in result.flags:
            flag_table.add_row(
                f.code,
                f"[{_VERDICT_STYLE[f.severity]}]{f.severity.name}[/]",
                f.message,
            )
        console.print(flag_table)
