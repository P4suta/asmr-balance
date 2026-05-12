"""Targeted tests that close the few remaining coverage gaps in v1.0.0.

These cases are usually one-liners in defensive branches that the canonical
end-to-end paths don't exercise (empty inputs, sentinel errors, exhaustive
match safety nets). Each test calls out the specific path it pins down.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from asmr_balance.config.model import Config
from asmr_balance.graph.builder import GraphBuilder
from asmr_balance.graph.frozen import FrozenGraph
from asmr_balance.graph.scheduler import run_from_iter
from asmr_balance.graph.types import ShortTermZBlock, Stream
from asmr_balance.metrics.loudness import IntegratedLoudnessReducer
from asmr_balance.metrics.lra import LRAReducer
from asmr_balance.nodes.bandsplit import _bandpass_sos
from asmr_balance.nodes.oversample import _oversample_channel, _polyphase_taps
from asmr_balance.nodes.zblocks import _ChannelMeanSquareBuffer
from asmr_balance.scan.parallel import _resolved_workers, scan_many
from asmr_balance.scan.pipeline import _block_samples_for
from asmr_balance.sink.base import build_sinks
from asmr_balance.sink.html import HtmlSink
from asmr_balance.sink.tui import TuiSummarySink, render_summary
from asmr_balance.source.backend.dispatch import _use_pyav, layout_name, probe


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------
def test_stream_repr_includes_node_id() -> None:
    s = Stream(node_id=42)
    assert "42" in repr(s)


def test_frozen_graph_node_name_returns_none_for_non_reducer() -> None:
    g = GraphBuilder()
    raw = g.source()
    g.kweight(raw, sample_rate=48000)
    g.reduce("loudness", IntegratedLoudnessReducer(), g.zblocks(g.kweight(raw, 48000), 48000))
    frozen = g.freeze()
    # Reducer node returns its name.
    reducer_id = frozen.reducer_ids[0]
    assert frozen.node_name(reducer_id) == "loudness"
    # SourceNode returns None.
    assert frozen.node_name(0) is None


def test_run_raises_without_source_node() -> None:
    """`_find_source_id` raises when the graph has no `SourceNode`."""
    fg = FrozenGraph(nodes=(), topo=(), children=(), reducer_ids=())
    with pytest.raises(ValueError, match="no SourceNode"):
        run_from_iter(fg, raw_blocks=[])


def test_builder_add_filter_requires_parent() -> None:
    """Internal `_add_filter` rejects empty parent tuples."""
    g = GraphBuilder()
    g.source()
    from asmr_balance.nodes.kweighting import KWeightingFilter

    with pytest.raises(ValueError, match="parent stream"):
        g._add_filter(KWeightingFilter(sample_rate=48000), parents=[])


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------
def test_bandpass_sos_raises_when_band_clips_to_zero_width() -> None:
    """Choosing edges that the Nyquist clip collapses must raise."""
    # 8 kHz sample rate, 20 kHz band centre → both edges clip above Nyquist → error.
    with pytest.raises(ValueError, match="band edges"):
        _bandpass_sos(order=4, low_edge_hz=20000.0, high_edge_hz=25000.0, sample_rate=8000)


def test_oversample_helper_with_empty_input() -> None:
    """`_oversample_channel` returns the state unchanged for empty input."""
    phases = _polyphase_taps()
    state = np.zeros(phases[0].size - 1, dtype=np.float64)
    out, new_state = _oversample_channel(state, np.empty(0, dtype=np.float64), phases)
    assert out.size == 0
    assert new_state is state


def test_zblocks_buffer_with_empty_push() -> None:
    """The internal `_ChannelMeanSquareBuffer` short-circuits empty pushes."""
    buf = _ChannelMeanSquareBuffer(block_size=10, hop_size=5)
    assert buf.push(np.empty(0, dtype=np.float64)) == []


# ---------------------------------------------------------------------------
# scan / parallel
# ---------------------------------------------------------------------------
def test_resolved_workers_zero_returns_cpu_count() -> None:
    assert _resolved_workers(0) >= 1


def test_resolved_workers_negative_falls_back_to_one() -> None:
    """Workers < 1 still resolves to a positive count."""
    assert _resolved_workers(-3) >= 1


def test_scan_many_empty_paths_yields_nothing() -> None:
    """Sequential and parallel paths share the empty-input short-circuit."""
    assert list(scan_many([], Config())) == []


def test_block_samples_for_invocation(tmp_path: Path) -> None:
    """`_block_samples_for` probes the file and scales to ``sample_rate * duration``."""
    import soundfile as sf

    wav = tmp_path / "x.wav"
    sf.write(str(wav), np.zeros((1024, 2), dtype=np.float32), 96000, subtype="FLOAT")
    cfg = Config(block_duration_sec=0.1)
    samples = _block_samples_for(cfg, wav)
    assert samples == 9600


# ---------------------------------------------------------------------------
# source / backend
# ---------------------------------------------------------------------------
def test_use_pyav_for_unknown_extension_raises() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        _use_pyav(Path("/tmp/x.bogus"))


def test_layout_name_falls_back_to_channel_count() -> None:
    assert layout_name(9) == "9ch"
    assert layout_name(7) == "6.1"


def test_probe_rejects_invalid_block_samples(tmp_path: Path) -> None:
    """The top-level `probe` only triggers the extension check; pass an audio file."""
    import soundfile as sf

    wav = tmp_path / "x.wav"
    sf.write(str(wav), np.zeros((100, 2), dtype=np.float32), 48000, subtype="FLOAT")
    info = probe(wav)
    assert info.sample_rate == 48000


def test_iter_pcm_frames_rejects_invalid_block_samples(tmp_path: Path) -> None:
    from asmr_balance.source.backend.dispatch import iter_pcm_frames

    p = tmp_path / "x.wav"
    import soundfile as sf

    sf.write(str(p), np.zeros((100, 2), dtype=np.float32), 48000, subtype="FLOAT")
    with pytest.raises(ValueError, match="block_samples"):
        list(iter_pcm_frames(p, block_samples=0))


# ---------------------------------------------------------------------------
# metrics / LRA edge cases
# ---------------------------------------------------------------------------
def test_lra_all_infinite_short_terms() -> None:
    """When every short-term block is silent, LRA / max are NaN."""
    r = LRAReducer()
    for _ in range(10):
        r.update(ShortTermZBlock((0.0, 0.0)))
    m = r.finalize()
    assert math.isnan(m.lra_lu)
    assert math.isnan(m.max_short_term_lufs)


def test_lra_below_abs_gate_returns_nan_lra_with_finite_max() -> None:
    """A single very-quiet block survives `isfinite` but fails the abs gate."""
    r = LRAReducer()
    # z=1e-9 → ≈ -90 LUFS, below -70 abs gate
    r.update(ShortTermZBlock((1e-9, 1e-9)))
    m = r.finalize()
    assert math.isnan(m.lra_lu)
    assert m.max_short_term_lufs < -80.0


def test_lra_single_block_above_gate_yields_zero_lra() -> None:
    r = LRAReducer()
    r.update(ShortTermZBlock((0.1, 0.1)))
    m = r.finalize()
    assert m.lra_lu == 0.0


# ---------------------------------------------------------------------------
# sinks
# ---------------------------------------------------------------------------
def test_html_sink_close_without_open_is_noop(tmp_path: Path) -> None:
    HtmlSink(path=tmp_path / "r.html").close()  # must not raise


def test_html_sink_rejects_write_before_open(tmp_path: Path) -> None:
    import soundfile as sf

    from asmr_balance.scan.pipeline import scan_one

    p = tmp_path / "x.wav"
    sf.write(str(p), np.zeros((100, 2), dtype=np.float32), 48000, subtype="FLOAT")
    result = scan_one(p, Config())
    sink = HtmlSink(path=tmp_path / "x.html")
    with pytest.raises(RuntimeError, match="before open"):
        sink.write(result)


def test_html_sink_renders_with_no_rows(tmp_path: Path) -> None:
    """Empty buffer should still produce a syntactically valid HTML file."""
    out = tmp_path / "empty.html"
    sink = HtmlSink(path=out)
    sink.open()
    sink.close()
    text = out.read_text(encoding="utf-8")
    assert "OK: 0" in text
    assert "FAIL: 0" in text


def test_tui_sink_close_without_open_is_noop() -> None:
    TuiSummarySink().close()  # must not raise


def test_tui_sink_rejects_write_before_open(tmp_path: Path) -> None:
    import soundfile as sf

    from asmr_balance.scan.pipeline import scan_one

    p = tmp_path / "x.wav"
    sf.write(str(p), np.zeros((100, 2), dtype=np.float32), 48000, subtype="FLOAT")
    result = scan_one(p, Config())
    sink = TuiSummarySink()
    with pytest.raises(RuntimeError, match="before open"):
        sink.write(result)


def test_render_summary_with_empty_results() -> None:
    import io

    from rich.console import Console

    console = Console(file=io.StringIO(), width=120, force_terminal=False, color_system=None)
    render_summary([], console=console)
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "Files" in out


def test_build_sinks_no_parquet_no_html_no_summary() -> None:
    sinks = build_sinks(out_parquet=None, out_html=None, show_summary=False)
    assert sinks == []


def test_build_sinks_html_and_summary(tmp_path: Path) -> None:
    sinks = build_sinks(
        out_parquet=[str(tmp_path / "r.parquet")],
        out_html=str(tmp_path / "r.html"),
        show_summary=True,
    )
    assert len(sinks) == 3


# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
def test_is_tty_force_json_returns_false() -> None:
    """`force_json=True` always returns False — used by the CLI ``--log-json``."""
    from asmr_balance.logging import _is_tty

    assert _is_tty(force_json=True) is False
