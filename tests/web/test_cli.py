from __future__ import annotations

from typing import Any

import pytest

from asmr_balance.web import cli


def test_main_invokes_uvicorn_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(target: str, **kwargs: Any) -> None:
        captured["target"] = target
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.delenv("ASMR_WEB_HOST", raising=False)
    monkeypatch.delenv("ASMR_WEB_PORT", raising=False)
    monkeypatch.delenv("ASMR_BALANCE_LOG_LEVEL", raising=False)

    cli.main()

    assert captured["target"] == "asmr_balance.web.app:create_app"
    assert captured["kwargs"]["host"] == cli.DEFAULT_HOST
    assert captured["kwargs"]["port"] == cli.DEFAULT_PORT
    assert captured["kwargs"]["factory"] is True


def test_main_respects_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(target: str, **kwargs: Any) -> None:
        captured["target"] = target
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setenv("ASMR_WEB_HOST", "127.0.0.1")
    monkeypatch.setenv("ASMR_WEB_PORT", "9876")
    monkeypatch.setenv("ASMR_BALANCE_LOG_LEVEL", "WARNING")

    cli.main()

    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["port"] == 9876
