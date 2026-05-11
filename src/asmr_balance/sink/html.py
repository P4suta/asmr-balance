"""HTML sink — Jinja2 template + Plotly bar chart of per-file ΔLU."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, BaseLoader, select_autoescape

from asmr_balance.sink.base import result_to_flat_row

if TYPE_CHECKING:
    from asmr_balance.scan.pipeline import FileResult


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>asmr-balance report</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }
    h1 { font-size: 1.5rem; }
    .summary { display: flex; gap: 1rem; margin-bottom: 1rem; }
    .pill { padding: 0.4rem 0.8rem; border-radius: 999px; font-weight: 600; }
    .ok { background: #d1fae5; color: #065f46; }
    .warn { background: #fef3c7; color: #92400e; }
    .fail { background: #fee2e2; color: #991b1b; }
    table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
    th, td { padding: 0.4rem 0.6rem; border-bottom: 1px solid #e5e7eb; text-align: left; }
    th { background: #f3f4f6; }
    tr.fail { background: #fef2f2; }
    tr.warn { background: #fffbeb; }
  </style>
</head>
<body>
  <h1>asmr-balance report</h1>
  <div class="summary">
    <span class="pill ok">OK: {{ count_ok }}</span>
    <span class="pill warn">WARN: {{ count_warn }}</span>
    <span class="pill fail">FAIL: {{ count_fail }}</span>
    <span>files: {{ rows | length }}</span>
  </div>
  <div id="chart" style="height: 360px;"></div>
  <table>
    <thead>
      <tr>
        <th>file</th>
        <th>verdict</th>
        <th>ΔLU</th>
        <th>p95 ΔLU</th>
        <th>Pearson r</th>
        <th>dBTP max</th>
        <th>LRA</th>
        <th>flags</th>
      </tr>
    </thead>
    <tbody>
    {% for row in rows %}
      <tr class="{{ row.verdict.lower() }}">
        <td>{{ row['meta.file_path'] }}</td>
        <td>{{ row.verdict }}</td>
        <td>{{ _fmt(row['loudness.delta_lu']) }}</td>
        <td>{{ _fmt(row['sliding.p95_lu']) }}</td>
        <td>{{ _fmt(row['correlation.pearson_r']) }}</td>
        <td>{{ _fmt(row['dynamics.true_peak_dbtp_max']) }}</td>
        <td>{{ _fmt(row['lra.lra_lu']) }}</td>
        <td>{{ row.flag_codes | join(', ') }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  <script>
    Plotly.newPlot('chart', [{
      type: 'bar',
      x: {{ chart_x | tojson }},
      y: {{ chart_y | tojson }},
      marker: { color: {{ chart_color | tojson }} },
    }], {
      title: 'ΔLU per file (L − R, LU)',
      margin: { t: 40, b: 80 },
      xaxis: { tickangle: -45 },
    }, { responsive: true });
  </script>
</body>
</html>
"""


_VERDICT_COLOUR = {"OK": "#10b981", "WARN": "#f59e0b", "FAIL": "#ef4444"}


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    try:
        if value != value:  # NaN
            return "NaN"
        if value == float("inf"):
            return "+∞"
        if value == float("-inf"):
            return "−∞"
        return f"{value:.2f}"
    except TypeError:
        return str(value)


@dataclass(slots=True)
class HtmlSink:
    """Buffer rows; render Jinja2 + Plotly HTML on :meth:`close`."""

    path: str | Path
    _rows: list[dict] = field(default_factory=list, init=False)
    _opened: bool = field(default=False, init=False)

    def open(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._opened = True
        self._rows = []

    def write(self, result: FileResult) -> None:
        if not self._opened:
            msg = "HtmlSink.write called before open"
            raise RuntimeError(msg)
        self._rows.append(result_to_flat_row(result))

    def close(self) -> None:
        if not self._opened:
            return
        env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
        env.globals["_fmt"] = _fmt
        template = env.from_string(_TEMPLATE)
        x_labels = [Path(r["meta.file_path"]).name for r in self._rows]
        y_values = [r["loudness.delta_lu"] for r in self._rows]
        colours = [_VERDICT_COLOUR.get(r["verdict"], "#6b7280") for r in self._rows]
        html = template.render(
            rows=self._rows,
            count_ok=sum(1 for r in self._rows if r["verdict"] == "OK"),
            count_warn=sum(1 for r in self._rows if r["verdict"] == "WARN"),
            count_fail=sum(1 for r in self._rows if r["verdict"] == "FAIL"),
            chart_x=x_labels,
            chart_y=[v if v is not None and v == v else 0.0 for v in y_values],
            chart_color=colours,
        )
        Path(self.path).write_text(html, encoding="utf-8")
        self._opened = False
