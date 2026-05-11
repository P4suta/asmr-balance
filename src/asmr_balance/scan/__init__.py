"""Pipeline composition + ProcessPool-backed parallelism."""

from __future__ import annotations

from asmr_balance.scan.parallel import scan_many
from asmr_balance.scan.pipeline import FileResult, scan_one
from asmr_balance.scan.assemble import build_default_graph

__all__ = ["FileResult", "build_default_graph", "scan_many", "scan_one"]
