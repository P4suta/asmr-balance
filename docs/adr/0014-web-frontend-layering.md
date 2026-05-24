# 0014 — Web frontend as primary interface, layered into HTTP / use case / DTO

- Status: Accepted
- Date: 2026-05-24
- Deciders: @P4suta

## Context

Through ADR-0001…0013 asmr-balance grew a rigorous batch CLI: streaming
SignalGraph, rule algebra over a verdict semilattice, parquet + HTML + Rich
sinks. The CLI is correct and complete, but the audience that benefits most
from L/R balance diagnostics — ASMR producers, distributors, listeners —
will not type `just scan /path/to/library` from a shell.

The first interface they encounter must instead be a browser. From this
release on, the Web UI is the **primary** entry point; the CLI persists as
the canonical CI / automation surface.

The transformation must not corrupt the analysis core. The pipeline already
exposes clean entry points (`scan_one`, `scan_many`, `Sink` protocol,
`MetricRecord` Pydantic models). The web layer must consume them without
mutation and without leaking HTTP / template concerns down into the domain.

## Decision

### Primary entry

| Component | Mechanism |
| --- | --- |
| HTTP framework | **FastAPI** — Pydantic v2 native, OpenAPI auto-generated, SSE / DI built-in. The DTOs reuse `MetricRecord` as embedded models, so the wire schema is the same as the domain schema. |
| Frontend | **HTMX + Jinja2 + Plotly** (browser-side CDN). No SPA framework. Server-rendered partials swap into the page; minimal JS. |
| Process serving | **uvicorn** inside the existing `app` Docker image (new compose service `web`). Container binds `0.0.0.0:8000`; the compose port mapping uses `127.0.0.1:8000:8000` so the listener is only reachable from the host loopback. |
| Background work (Phase 1b) | **In-process asyncio + thread offload**; scan jobs are tracked in an in-memory `JobRegistry`. The scan worker count is forced to `1` in web mode because the existing `ProcessPoolExecutor`-backed `scan_many` invokes sinks in child processes — sink callbacks cannot push to a parent-process `asyncio.Queue`. The trade-off is acceptable because the SSE narrative is naturally sequential. |
| Authn / authz | None. Localhost-only single-user assumption. |

### Layering

The web package is split into four layers; each lower layer is ignorant of
the one above it:

```
HTTP boundary    src/asmr_balance/web/routes/{inspect,scan,…}.py
       │  parses request, translates domain errors to HTTPException
       ▼
Use cases        src/asmr_balance/web/use_cases/{inspect,scan,…}.py
       │  pure Python in/out — no Request, no template, no HTTP types
       ▼
Domain           src/asmr_balance/{scan,sink,source,metrics,…}    (unchanged)
       ▲
       │  Pydantic wire models constructed from domain values via
       │  classmethods (`from_file_result`, `from_flag`, …)
DTOs             src/asmr_balance/web/dto.py
```

Routes do exactly two things: HTTP adaptation and DTO construction. Use cases
own orchestration (tempfile lifecycle, config selection). The domain stays
free of any HTTP coupling.

### De-duplication

Audio file extensions are accepted by both the CLI walker
(`src/asmr_balance/cli.py:_find_audio_files`) and the web upload validator
(`web/use_cases/inspect.py:perform_inspect`). The list lives in exactly one
place: `src/asmr_balance/source/audio_extensions.py:AUDIO_EXTENSIONS`. Both
CLI and web import it; drift is impossible.

### Resource resolution

Templates and static assets ship inside the wheel
(`pyproject.toml:tool.hatch.build.targets.wheel.artifacts`). Their absolute
filesystem paths are resolved through `importlib.resources.files`, centralized
in `src/asmr_balance/web/resources.py`. The FastAPI factory consumes
`TEMPLATES_DIR` / `STATIC_DIR` constants; no module computes them ad-hoc.

## Consequences

**Positive**

- Adding a new endpoint requires editing exactly three files (route adapter,
  use case, DTO). Adding a new delivery channel (TUI, webhook, MCP) reuses
  the use cases unchanged.
- The OpenAPI schema is generated from the same Pydantic models the pipeline
  emits — clients get accurate types for free.
- The analysis core never imports from `web/`. Future ADRs about DSP science
  remain orthogonal to delivery decisions.

**Negative / accepted**

- Scan jobs are sequential in web mode (workers=1). Bulk users keep the CLI
  for parallelism. Phase 2 may revisit via `multiprocessing.Queue → asyncio.Queue`
  bridging if the SSE narrative becomes a bottleneck.
- The in-memory `JobRegistry` (Phase 1b) loses history on restart. Acceptable
  for single-user local use; SQLite persistence is deferred to Phase 3.
- Two response shapes for inspect (`/api/inspect` JSON, `/api/inspect/partial`
  HTML) share one use case but live as two route handlers. Cleaner than
  content negotiation given HTMX's `hx-post` ergonomics.

## Phasing

- **1a** — `/healthz`, `/api/schema`, `/api/inspect{,/partial}`, index page,
  HTMX D&D.
- **1b** — `JobRegistry`, `JsonStreamingSink`, `/api/scan`,
  `/api/scan/{id}/events` (SSE), `/api/scan/{id}/report.{parquet,html,json}`,
  `/api/library`, scan tab.
- **2** — Plotly visualization (1/3-octave band ΔLU bars, sliding ΔLU timeline,
  true peak markers).
- **3** — Config override UI, threshold profile presets, history persistence,
  dark mode.

## References

- `src/asmr_balance/web/` — implementation root.
- ADR-0011 (SignalGraph), ADR-0012 (Rule algebra & Verdict semilattice) —
  the domain protocols the web layer wraps.
- `plans/.../asm-fancy-rabin.md` — the original architecture plan; this ADR
  formalizes its load-bearing decisions.
