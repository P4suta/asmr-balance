# 0015 — Web streaming over NDJSON (inspect + scan)

- Status: Accepted
- Date: 2026-05-24
- Deciders: @P4suta
- Supersedes: nothing (extends [0014](0014-web-frontend-layering.md))

## Context

Phase 2.5 finished with the inspect form running as one round-trip HTMX
POST against `/api/inspect/partial`. The browser saw an indeterminate
loading bar and a wall-clock tick while the server churned silently for the
duration of the scan. There was no truth flowing from server to client
between "request sent" and "HTML received."

The listener-pivot rework also surfaced an inconsistency: the multi-file
`/api/scan/{id}/events` endpoint already streamed per-file progress over
`text/event-stream` (SSE via `sse-starlette`), but the single-file inspect
form — the primary entry point — did not. We had two parallel UX qualities
in the same product.

A first pass mirrored the existing scan transport: add `POST
/api/inspect/stream` as a second SSE endpoint. During review the user
pushed back: *"SSE なんて微妙なことせずに …もっとモダンでスマートな解法を考えて
くれていいよ"*. We re-evaluated transports.

## Decision

Adopt **NDJSON over HTTP/1.1 chunked `StreamingResponse`** as the *only*
streaming wire format the web layer exposes. Both single-file inspect and
multi-file scan are migrated; SSE is removed from the codebase entirely and
the `sse-starlette` dependency is dropped from `pyproject.toml` /
`uv.lock`. Specifically:

1. `POST /api/inspect/stream` accepts the multipart upload and returns
   `application/x-ndjson`. One JSON object per line, three frame shapes
   discriminated by `type`:
   - `progress` — `{stage, current, total}` ticked at every pipeline
     boundary and per audio block during `analyze`.
   - `done`     — `{html}` carrying the rendered result-card partial; last
     frame on the success path.
   - `failed`   — `{error, detail, status, context}`; last frame on any
     failure path (domain or programmer error).
2. `GET /api/scan/{id}/stream` returns the same media type. One
   `{type:"file_done", sequence, total, source_name, verdict, …}` per file
   plus a terminal frame:
   - `done`   — empty payload, job completed cleanly.
   - `failed` — `{detail}` mirroring `Job.failed_reason` when the background
     task crashed mid-flight.
3. Neither route flips HTTP status mid-stream. Once headers are committed
   (HTTP 200) every failure surfaces as a `failed` frame, including
   pre-stream rejections like an unsupported suffix. Client code is a
   uniform `fetch → for await frame → dispatch on frame.type`.
4. The browser consumes both endpoints via the same helper:
   `Response.body.pipeThrough(new TextDecoderStream()).getReader()` driving
   a line-buffered NDJSON async generator — no external client library, no
   `EventSource`.
5. The inspect form drops every `hx-*` attribute; HTMX is no longer used
   anywhere in the codebase and the script tag in `base.html` is removed.

The internal abstractions stay transport-agnostic:

- `graph.scheduler.run` grew an `on_block: (done, total) -> None` keyword.
- `scan.pipeline.scan_one` grew an `on_progress: (stage, current, total)
  -> None` keyword with stable stage tokens
  (`probe/decode/analyze/assemble/evaluate/complete/skipped`).
- `web.use_cases.inspect.perform_inspect_streaming` is an `async` generator
  yielding `InspectProgressEvent | FileResult`. It bridges the sync scan
  pipeline to the async world with `asyncio.to_thread` + a `Queue` (`None`
  sentinel for "worker done").
- `web.dto.InspectProgressEvent / InspectDoneEvent / InspectFailedEvent`
  are the wire models.

The route is a thin frame-wrapper around the async generator.

## Why NDJSON, not SSE or WebSocket

| Concern                       | NDJSON chunked                 | SSE (`text/event-stream`) | WebSocket                      |
| ----------------------------- | ------------------------------ | ------------------------- | ------------------------------ |
| Direction                     | server → client                | server → client           | bidirectional (we don't need)  |
| Round trips                   | 1 (POST + streamed response)   | 2 (POST job, GET events)  | 2 (POST upload, WS connect)    |
| Client API                    | `fetch + ReadableStream` only  | `EventSource` (GET only)  | `WebSocket` + framing          |
| Request body / headers        | full multipart upload          | none (GET only)           | custom subprotocol             |
| Wire shape                    | one JSON object per line       | `event:`/`data:` framing  | binary or text frames          |
| Proxy / nginx requirements    | none                           | none                      | upgrade handshake config       |
| Server dep                    | `StreamingResponse` (built-in) | `sse-starlette`           | starlette WebSocket            |
| Industry precedent for AI/ML  | OpenAI / Anthropic / Vercel    | older dashboards          | chat / collaboration tools     |

WebSocket is overkill — cancellation is `AbortController` + Starlette's
`request.is_disconnected()`. SSE's `EventSource` cannot carry a multipart
body, forcing a two-step "POST job → GET events" dance that the multi-file
scan endpoint accepts but is wrong for an in-line "process this one file
and stream the result" interaction.

## Consequences

### Positive

- Single round-trip submission, real per-stage progress bar driven by
  weighted stage fractions (analyze dominates at 85 %).
- One uniform wire shape for every outcome — no mid-stream status flips,
  no client-side branching on HTTP status vs. frame type.
- HTMX dependency removed in full; only Plotly and the inline theme script
  remain in `base.html`.
- Internal `on_progress` / `on_block` contracts are wire-agnostic, so a
  future transport swap (WebSocket binary, msgpack streaming, etc.) is a
  route-layer edit, not a use-case-layer rewrite.

### Negative

- The inspect form now hard-requires JavaScript. The previous HTMX path
  worked without JS for the basic submit. Mitigation: the JSON endpoint
  `POST /api/inspect` and the HTML endpoint `POST /api/inspect/partial`
  remain available for scripted / curl consumers.
- The scan event endpoint moved from `/events` to `/stream` and the wire
  format changed from `text/event-stream` to NDJSON. Any external
  consumer using `EventSource` against the previous URL must switch to a
  `fetch()` + `ReadableStream` reader (or just `curl -N`). Acceptable
  because this is a self-hosted tool with no third-party clients.

### Neutral

- 100 % branch coverage gate is maintained. The `except Exception` branch
  in the streaming route is exercised by a monkeypatched test that injects a
  `RuntimeError` from the use case.

## Implementation pointers

- Inspect route: `src/asmr_balance/web/routes/inspect.py::inspect_stream`.
- Inspect use case: `src/asmr_balance/web/use_cases/inspect.py::perform_inspect_streaming`.
- Scan route: `src/asmr_balance/web/routes/scan.py::scan_stream`.
- Scan sink bridge: `src/asmr_balance/web/runtime/sinks.py::JsonStreamingSink`.
- Pipeline callback: `src/asmr_balance/scan/pipeline.py::scan_one` (`on_progress` kwarg).
- Scheduler callback: `src/asmr_balance/graph/scheduler.py::run` (`on_block` kwarg).
- DTOs: `src/asmr_balance/web/dto.py` — `InspectProgressEvent` /
  `InspectDoneEvent` / `InspectFailedEvent` /
  `ScanFileEvent` / `ScanDoneEvent` / `ScanFailedEvent`.
- Client: `src/asmr_balance/web/static/app.js` — `runInspect` /
  `consumeScanStream` / `ndjsonFrames` (shared reader).

## Verification

- `pytest tests/web/test_inspect.py tests/unit/scan/test_pipeline.py
  tests/unit/graph/test_scheduler.py tests/web/test_scan_route.py` covers
  stage emission, frame shape, pre-stream rejection, mid-stream decode
  failure, programmer-bug fallback, scan crash-as-`failed`-frame, and the
  SKIPPED-but-still-`done` path. 100 % branch coverage maintained.
- Manual curl smoke: `curl -sN -F file=@panned.wav
  http://127.0.0.1:8000/api/inspect/stream` confirms incremental flush
  (analyze ticks ~8 ms apart on a sub-second scan, no buffering).
