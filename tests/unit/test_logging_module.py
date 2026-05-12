"""Cover the structlog setup edge cases in :mod:`asmr_balance.logging`."""

from __future__ import annotations

import os

import structlog

from asmr_balance.logging import configure_logging, get_logger


def teardown_module() -> None:
    structlog.reset_defaults()


def test_get_logger_returns_bound_logger() -> None:
    configure_logging(level="INFO")
    logger = get_logger("test")
    logger.info("event", key=1)


def test_configure_logging_with_invalid_level_falls_back_to_info() -> None:
    configure_logging(level="NOT_A_LEVEL")
    logger = get_logger("test2")
    logger.info("event_after_bad_level")


def test_configure_logging_reads_env_var(monkeypatch) -> None:
    monkeypatch.setenv("ASMR_BALANCE_LOG_LEVEL", "DEBUG")
    configure_logging(level=None)
    logger = get_logger("test3")
    logger.debug("event")


def test_configure_logging_json_mode() -> None:
    configure_logging(level="INFO", json=True)
    logger = get_logger("test4")
    logger.info("event_json")
