"""Wrapper for ``mutmut run`` that patches the wall-clock timeout multiplier.

mutmut 3.x hardcodes ``timeout = (estimated + 1) * 15`` (wall clock); with
fast unit tests (~5 ms baseline), the resulting 15 s ceiling is shorter than
the pytest fork startup we observe (~3–6 s) plus margin, so every mutation
gets killed by ``SIGXCPU`` before its test can finish.

This wrapper monkey-patches the multiplier to a much larger value so the
wall-clock timeout becomes generous enough for our suite. CPU-time limit is
patched too, although it is normally not the binding constraint.

Usage:
    python scripts/run_mutmut.py run --max-children 4 [other mutmut args]
"""

from __future__ import annotations

import sys
from datetime import datetime
from time import sleep
from typing import Any

import mutmut.__main__ as _m

_WALL_MULT = 300
_CPU_MULT = 300


def _patched_timeout_checker(mutants: list[Any]) -> Any:
    import os
    import signal

    def inner() -> None:
        while True:
            sleep(1)
            now = datetime.now()
            for m, mutant_name, _result in mutants:
                with _m.START_TIMES_BY_PID_LOCK:
                    start_times_by_pid = dict(m.start_time_by_pid)
                est = m.estimated_time_of_tests_by_mutant.get(mutant_name, 0.0)
                for pid, start_time in start_times_by_pid.items():
                    if (now - start_time).total_seconds() > (est + 1) * _WALL_MULT:
                        try:
                            os.kill(pid, signal.SIGXCPU)
                        except ProcessLookupError:
                            pass

    return inner


_m.timeout_checker = _patched_timeout_checker


# Also patch ``ceil((est + 1) * 30 + process_time())`` so the CPU rlimit is
# generous. mutmut hard-codes ``* 30`` inline inside the fork body; we can't
# monkey-patch a line of code, but we *can* swap ``resource.setrlimit`` with
# a generous wrapper that raises the multiplier transparently.
import resource as _resource  # noqa: E402

_orig_setrlimit = _resource.setrlimit


def _generous_setrlimit(which: int, limits: tuple[int, int]) -> None:
    if which == _resource.RLIMIT_CPU:
        soft, hard = limits
        soft = max(soft, _CPU_MULT)
        hard = max(hard, _CPU_MULT + 1)
        limits = (soft, hard)
    _orig_setrlimit(which, limits)


_resource.setrlimit = _generous_setrlimit


def main() -> None:
    if len(sys.argv) <= 1:
        sys.argv += ["run"]
    sys.argv[0] = "mutmut"
    _m.cli()


if __name__ == "__main__":
    main()
