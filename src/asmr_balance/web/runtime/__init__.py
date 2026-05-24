"""In-process runtime for the web layer (job registry, sinks, path roots).

The runtime layer owns whatever stateful glue the use cases need; the use
cases themselves stay free of side-effecting state. Keeping this separate
means the use cases remain testable in isolation by passing in a fresh
:class:`JobRegistry` per call, and means future replacements (e.g. a Redis-
backed registry) can be substituted at the runtime boundary only.
"""
