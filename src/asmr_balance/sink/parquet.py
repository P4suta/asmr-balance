"""Parquet sink — buffer rows, write on ``close``.

The schema is the flat dotted name space from
:mod:`asmr_balance.sink.base`. Buffering in memory is fine because each row
is < 1 KB and typical scans process at most a few thousand files; if a future
deployment needs streaming row groups, polars supports it via
:meth:`pl.DataFrame.write_parquet` with row-group sizing, but the current
ergonomics favor a single atomic write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from asmr_balance.sink.base import COLUMN_NAMES, result_to_flat_row

if TYPE_CHECKING:
    from asmr_balance.scan.pipeline import FileResult


@dataclass(slots=True)
class ParquetSink:
    """Buffer :class:`FileResult` rows; emit a parquet file on :meth:`close`."""

    path: str | Path
    compression: str = "zstd"
    _rows: list[dict] = field(default_factory=list, init=False)
    _opened: bool = field(default=False, init=False)

    def open(self) -> None:
        # Ensure the parent directory exists; fail fast on permission errors.
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._opened = True
        self._rows = []

    def write(self, result: FileResult) -> None:
        if not self._opened:
            msg = "ParquetSink.write called before open"
            raise RuntimeError(msg)
        self._rows.append(result_to_flat_row(result))

    def close(self) -> None:
        if not self._opened:
            return
        df = pl.DataFrame(self._rows, schema={name: _column_dtype(name) for name in COLUMN_NAMES})
        df.write_parquet(self.path, compression=self.compression)
        self._opened = False


def _column_dtype(column: str) -> pl.PolarsDataType:
    if column in {"meta.file_path", "meta.channel_layout", "status", "skip_reason", "verdict"}:
        return pl.Utf8
    if column == "meta.sample_rate":
        return pl.Int64
    if column == "flag_codes":
        return pl.List(pl.Utf8)
    return pl.Float64
