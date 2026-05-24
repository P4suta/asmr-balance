"""Uvicorn launcher for the Web UI (``asmr-balance-web`` entrypoint).

Inside the container we always bind ``0.0.0.0``; the docker-compose host port
mapping restricts external exposure to ``127.0.0.1``. See
``docs/adr/0014-web-frontend-layering.md``.
"""

from __future__ import annotations

import os

import uvicorn

from asmr_balance.logging import configure_logging

# The container deliberately binds all interfaces; the docker-compose port
# mapping (127.0.0.1:<port>:8000) is what restricts external exposure to host
# loopback. See docs/adr/0014-web-frontend-layering.md.
DEFAULT_HOST = "0.0.0.0"  # noqa: S104  # nosec B104
DEFAULT_PORT = 8000


def main() -> None:
    """Entry point for ``asmr-balance-web`` script."""
    configure_logging(level=os.environ.get("ASMR_BALANCE_LOG_LEVEL"))
    host = os.environ.get("ASMR_WEB_HOST", DEFAULT_HOST)
    port = int(os.environ.get("ASMR_WEB_PORT", str(DEFAULT_PORT)))
    uvicorn.run(
        "asmr_balance.web.app:create_app",
        host=host,
        port=port,
        factory=True,
    )


if __name__ == "__main__":  # pragma: no cover -- module CLI safety net
    main()
