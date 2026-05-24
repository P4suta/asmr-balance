"""Use cases — application-level orchestration of domain APIs.

Each module exposes pure functions that take Python values in and return
domain values (``FileResult``, etc.). They never touch HTTP, Request, or
templates — the routing layer adapts use cases to the wire format via the
DTOs in :mod:`asmr_balance.web.dto`.
"""
