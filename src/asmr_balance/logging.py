"""Structured logging via structlog (ADR-0009).

TTY → pretty console renderer (colors).
Non-TTY (CI, pipe) → JSON renderer (one event per line).
All events carry ``timestamp``, ``level``, ``event``, ``module``.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Final

import structlog

if TYPE_CHECKING:
    from structlog.types import EventDict, Processor

_DEFAULT_LEVEL: Final[str] = "INFO"


def _is_tty(force_json: bool) -> bool:  # pragma: no cover -- TTY state depends on env
    if force_json:
        return False
    return sys.stderr.isatty()


def _drop_color_message_key(_: object, __: str, event_dict: EventDict) -> EventDict:
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging(level: str | None = None, *, json: bool = False) -> None:
    """Configure structlog + stdlib logging once at process start.

    Args:
        level: Log level name (DEBUG/INFO/WARNING/ERROR). Falls back to
            ``ASMR_BALANCE_LOG_LEVEL`` env var, then INFO.
        json: Force JSON output regardless of TTY detection.
    """
    resolved_level = (level or os.environ.get("ASMR_BALANCE_LOG_LEVEL") or _DEFAULT_LEVEL).upper()
    numeric_level = logging.getLevelName(resolved_level)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _drop_color_message_key,
    ]

    if _is_tty(force_json=json):  # pragma: no cover -- TTY mode tested manually
        renderer: Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=numeric_level, format="%(message)s", stream=sys.stderr)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to ``name`` (typically ``__name__``)."""
    return structlog.get_logger(name)
