# Research: TUI Dashboard

**Feature**: 005-tui-dashboard | **Date**: 2026-05-26

## Research Tasks

### RT-1: Textual 1.x structlog Integration Pattern

**Question**: How to bridge structlog events → Textual widget updates without breaking hexagonal bounds?

**Decision**: Custom structlog processor that posts Textual messages.

**Rationale**: A `structlog.ProcessorReturnType` processor added to the structlog chain can call `app.post_message()` when events match INFO+ level. This keeps logging config in infrastructure, keeps TUI as passive consumer. The processor is injected at app startup — the TUI never imports structlog directly for event capture.

**Alternatives Considered**:
- **Custom logging.Handler**: Would work but bypasses structlog's structured data — we'd lose context fields.
- **Polling a queue**: Adds latency and complexity. Message-passing is Textual-native.
- **File tailing**: Anti-pattern — adds filesystem I/O to TUI layer, violates hexagonal bounds.

### RT-2: Progress Tracking for PipelineRunner

**Question**: PipelineRunner currently returns `PipelineReport` at completion. How does TUI get mid-run progress?

**Decision**: Emit structlog INFO events with progress metadata (stage, current, total). TUI interprets these via the same structlog→message bridge.

**Rationale**: PipelineRunner already emits structlog events at each stage. Adding `current`/`total` context fields to existing events is minimally invasive. The TUI processor filters for events with `progress_current`/`progress_total` keys and updates progress widgets. This requires no new ports or callbacks — pure observation.

**Key events to emit**:
- `library_scan_started` (stage="scan", indeterminate=True)
- `library_scan_complete` (stage="scan", total=N)
- `episode_analysis_started` (stage="analysis", current=i, total=N)
- `episode_mux_started` (stage="mux", current=i, total=N)
- `episode_mux_complete` (stage="mux", current=i, total=N)
- `pipeline_complete` (stage="done")

**Alternatives Considered**:
- **Callback protocol/port**: Adds coupling. PipelineRunner would need a `ProgressPort` — over-engineered for observation.
- **asyncio.Queue**: Works but requires PipelineRunner to know about the queue — breaks DI purity.
- **Reactive model shared between layers**: Violates hexagonal — core would import reactive types.

### RT-3: Textual Worker Integration with PipelineRunner

**Question**: PipelineRunner.run() is async. How does TUI invoke it without blocking the event loop?

**Decision**: Use `self.run_worker(self._run_pipeline(config))` with `exclusive=True`. The worker coroutine wraps `PipelineRunner.run()` call.

**Rationale**: Textual's worker system is designed exactly for this. `exclusive=True` prevents concurrent pipeline runs (matching FR-012). The worker's async nature means `PipelineRunner.run()` (which uses `asyncio.gather()` internally) executes on the same event loop — no thread boundary issues.

**Alternatives Considered**:
- **Thread worker**: Unnecessary — PipelineRunner is already async, not CPU-bound.
- **Manual asyncio.create_task()**: Bypasses Textual's lifecycle management — worker cancel/error handling lost.

### RT-4: Activity Feed Throttling

**Question**: High-frequency structlog events (per-font-query) could overwhelm Textual rendering.

**Decision**: Buffer incoming log messages in the structlog processor. Flush to TUI at max 10 messages/second using a `set_timer()` based debounce in the TUI.

**Rationale**: Textual's `set_timer()` is the idiomatic way to schedule deferred UI updates. The processor buffers messages in a list; a recurring timer (100ms interval) drains the buffer and batch-appends to the Log widget. This keeps the event loop responsive.

**Alternatives Considered**:
- **Drop events**: Loses information — unacceptable for operator trust.
- **Aggregate/deduplicate**: Complex and lossy.
- **Rate-limit at structlog level**: Would affect file logging too — unacceptable.

### RT-5: TUI ↔ PipelineRunner Dependency Injection

**Question**: How does the TUI app get a configured PipelineRunner instance?

**Decision**: Factory function in `src/tui/bootstrap.py` that constructs all adapters and injects them into PipelineRunner, then passes the runner to the App constructor.

**Rationale**: Keeps TUI layer free of adapter construction details. The bootstrap function is the composition root — it imports adapters but the App class itself only depends on PipelineRunner (and transitively, its domain model return types). This matches the hexagonal pattern: composition root wires everything, layers stay ignorant of each other.

**Alternatives Considered**:
- **App constructs adapters**: Violates hexagonal — TUI would import adapter layer.
- **Global singleton**: Anti-pattern, untestable.
- **Framework DI container**: YAGNI — simple constructor injection suffices.
