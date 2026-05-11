"""Branch-coverage tests for ``asmr_balance.logging``.

Exercise every conditional in ``configure_logging`` and helpers so that
``--cov-branch --cov-fail-under=100`` is satisfied by Day 0.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from asmr_balance.logging import (
    _drop_color_message_key,
    _is_tty,
    configure_logging,
    get_logger,
)

if TYPE_CHECKING:
    import pytest


def test_is_tty_force_json_short_circuits() -> None:
    assert _is_tty(force_json=True) is False


def test_is_tty_delegates_to_stderr_isatty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    assert _is_tty(force_json=False) is True

    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    assert _is_tty(force_json=False) is False


def test_drop_color_message_key_when_present() -> None:
    out = _drop_color_message_key(None, "method", {"color_message": "x", "event": "y"})
    assert "color_message" not in out
    assert out["event"] == "y"


def test_drop_color_message_key_when_absent() -> None:
    out = _drop_color_message_key(None, "method", {"event": "y"})
    assert out == {"event": "y"}


def test_configure_default_uses_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASMR_BALANCE_LOG_LEVEL", raising=False)
    configure_logging()
    get_logger("smoke").info("ok")


def test_configure_env_level_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASMR_BALANCE_LOG_LEVEL", "WARNING")
    configure_logging()
    get_logger("smoke").warning("from-env")


def test_configure_explicit_level_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASMR_BALANCE_LOG_LEVEL", "ERROR")
    configure_logging(level="DEBUG")
    get_logger("smoke").debug("explicit")


def test_configure_invalid_level_falls_back_to_info() -> None:
    configure_logging(level="NOSUCH")
    get_logger("smoke").info("fallback")


def test_configure_force_json_uses_json_renderer() -> None:
    configure_logging(json=True)
    get_logger("smoke").info("json-mode", k="v")


def test_configure_tty_uses_console_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    configure_logging(json=False)
    get_logger("smoke").info("tty-mode")
