"""Output sinks — Parquet / HTML / TUI under a common :class:`Sink` protocol."""

from __future__ import annotations

from asmr_balance.sink.base import Sink, build_sinks, result_to_flat_row
from asmr_balance.sink.html import HtmlSink
from asmr_balance.sink.parquet import ParquetSink
from asmr_balance.sink.tui import (
    InspectRenderer,
    TuiSummarySink,
    render_inspect,
    render_summary,
)

__all__ = [
    "HtmlSink",
    "InspectRenderer",
    "ParquetSink",
    "Sink",
    "TuiSummarySink",
    "build_sinks",
    "render_inspect",
    "render_summary",
    "result_to_flat_row",
]
