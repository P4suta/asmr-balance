"""TOML loader for :class:`Config`.

The TOML schema is hierarchical to mirror the structured :class:`ThresholdSet`:

.. code:: toml

    gate_lufs = -70.0
    layout_policy = "downmix"
    block_samples = 4800
    workers = 4

    [thresholds.lr_balance]
    warn_lu = 3.0
    fail_lu = 6.0

    [thresholds.true_peak_clip]
    warn_dbtp = -1.0
    fail_dbtp = 0.0

Unknown keys are rejected (``extra="forbid"`` on every model).
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from asmr_balance.config.model import Config

if TYPE_CHECKING:
    from pathlib import Path


def load_config(path: Path) -> Config:
    """Load a :class:`Config` from a TOML file. Raises ``ValidationError`` on bad keys."""
    with path.open("rb") as fp:
        data = tomllib.load(fp)
    return Config.model_validate(data)
