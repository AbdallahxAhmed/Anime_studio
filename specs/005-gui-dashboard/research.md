# Research: GUI Dashboard

**Feature**: 005-gui-dashboard | **Date**: 2026-05-26

## R1: Flet Async Patterns — Background Tasks Without Blocking UI

**Decision**: Use `page.run_task()` for fire-and-forget background work from UI event handlers. Use `asyncio.create_task()` within already-async contexts. Pipeline execution runs as a single background task that emits status updates.

**Rationale**: Flet runs on a single `asyncio` event loop. `page.run_task()` is the idiomatic way to spawn background coroutines from Flet event handlers (which are sync by default but can be async). It integrates with Flet's update lifecycle — after the task modifies controls, calling `page.update()` or `control.update()` pushes changes to the client.

**Alternatives Considered**:
- `threading.Thread` — REJECTED. Constitution III forbids manual thread creation. Flet is async-native.
- Raw `asyncio.create_task()` from sync handlers — Works but `page.run_task()` is preferred because it handles exception propagation to Flet's error handler.

**Pattern**:
```python
async def run_pipeline(e):
    page.run_task(execute_pipeline, library_path, dry_run)

async def execute_pipeline(library_path: Path, dry_run: bool):
    config = PipelineConfig(library_path=library_path, dry_run=dry_run)
    report = await pipeline_runner.run(config)
    # Update UI with results
    results_table.update_from(report)
    page.update()
```

---

## R2: Flet + structlog Integration — Log Bridge to GUI Widgets

**Decision**: Create a custom structlog processor that captures log events into an `asyncio.Queue`. The GUI polls this queue on a throttled timer and renders entries as `ActivityEntry` messages in the activity feed.

**Rationale**: structlog processors form a pipeline. Adding a processor that intercepts INFO+ events and pushes them to a shared queue is non-invasive — it doesn't modify the existing logging config. The queue decouples log production (pipeline thread) from GUI consumption (Flet event loop).

**Alternatives Considered**:
- stdlib `logging.Handler` subclass — REJECTED. Would bypass structlog's processor chain and lose structured context fields.
- Direct callback from processor to GUI widget — REJECTED. Tight coupling. Would also cause thread safety issues if pipeline runs in `asyncio.to_thread()`.
- `asyncio.Queue` with polling — SELECTED. Clean decoupling, async-safe, compatible with throttling.

**Pattern**:
```python
import asyncio
from collections.abc import Callable

class GuiLogBridge:
    def __init__(self, queue: asyncio.Queue):
        self._queue = queue

    def __call__(self, logger, method_name, event_dict):
        level = event_dict.get("level", "info")
        if level in ("info", "warning", "error", "critical"):
            self._queue.put_nowait(event_dict)
        return event_dict  # pass through to next processor
```

---

## R3: Flet DataTable — Sortable Results Tables

**Decision**: Use `ft.DataTable` with `DataColumn` (sortable) and `DataRow`/`DataCell` for the post-run results table. Each row = one episode with status icon, font count, error summary.

**Rationale**: `ft.DataTable` is Flet's built-in Material Design table. Supports `on_sort` callback for column sorting, cell-level styling, and row selection. Sufficient for up to 50 episodes.

**Alternatives Considered**:
- Custom `ListView` with formatted rows — REJECTED. No built-in sort support, more code for tabular layout.
- `ft.ResponsiveRow` grid — REJECTED. Not semantically a table. Sorting would be manual.

**Pattern**:
```python
ft.DataTable(
    sort_column_index=0,
    sort_ascending=True,
    columns=[
        ft.DataColumn(ft.Text("Episode"), on_sort=handle_sort),
        ft.DataColumn(ft.Text("Status")),
        ft.DataColumn(ft.Text("Fonts"), numeric=True),
        ft.DataColumn(ft.Text("Errors")),
    ],
    rows=[...],  # populated from PipelineReport
)
```

---

## R4: Flet FilePicker — Native Directory Picker

**Decision**: Use `ft.FilePicker` with `get_directory_path()` for library path selection. The picker is added to `page.overlay` and triggered by a button click.

**Rationale**: `ft.FilePicker` wraps the native OS directory picker dialog. It's the only Flet-sanctioned way to pick directories. Works cross-platform. Returns the selected path via `on_result` callback.

**Alternatives Considered**:
- `ft.TextField` with manual path entry — Could supplement but not replace. No validation of path existence.
- System dialog via `tkinter.filedialog` — REJECTED. Constitution XI: don't add `tkinter` dependency. Flet has built-in picker.

**Pattern**:
```python
picker = ft.FilePicker(on_result=on_directory_selected)
page.overlay.append(picker)

def pick_directory(e):
    picker.get_directory_path(dialog_title="Select Anime Library")

def on_directory_selected(e: ft.FilePickerResultEvent):
    if e.path:
        library_path_display.value = e.path
        run_button.disabled = False
        page.update()
```

---

## R5: Flet ProgressBar + ProgressRing — Spinner and Determinate Progress

**Decision**: Use `ft.ProgressRing()` (no value = indeterminate spinner) for library scan phase. Use `ft.ProgressBar(value=n/total)` for mux job progress (determinate).

**Rationale**: Flet's Material Design progress widgets map directly to the spec requirements. `ProgressRing` without a value spins indefinitely (scanner phase). `ProgressBar` with a 0–1 float shows determinate progress (mux N/M). Both are lightweight controls.

**Alternatives Considered**:
- Custom animation widget — REJECTED. YAGNI. Built-in widgets suffice.
- Single `ProgressBar` for both phases — REJECTED. Spec requires distinct visual treatment (spinner vs bar).

**Pattern**:
```python
# Indeterminate (scanning)
scanner_ring = ft.ProgressRing(width=24, height=24, stroke_width=3)
scanner_label = ft.Text("Scanning library...")

# Determinate (muxing)
mux_bar = ft.ProgressBar(value=0, width=400)
mux_label = ft.Text("Muxing: 0/12 episodes")

# Update on progress event
def on_mux_progress(completed: int, total: int):
    mux_bar.value = completed / total
    mux_label.value = f"Muxing: {completed}/{total} episodes"
    mux_bar.update()
    mux_label.update()
```

---

## R6: Flet SnackBar + AlertDialog — Error Presentation

**Decision**: Use `ft.SnackBar` for non-critical dismissible notifications. Use `ft.AlertDialog` for critical modal errors that halt the pipeline.

**Rationale**: Direct mapping to constitution IV requirement: "GUI MUST present errors via Flet's SnackBar for non-critical notifications and AlertDialog for critical/modal errors." SnackBar auto-dismisses after a timeout. AlertDialog requires explicit user action.

**Alternatives Considered**:
- `ft.Banner` for persistent errors — Could supplement but SnackBar is sufficient for non-critical.
- Custom overlay panel — REJECTED. YAGNI. Built-in widgets match requirements exactly.

**Pattern**:
```python
# Non-critical: SnackBar
page.snack_bar = ft.SnackBar(
    content=ft.Text(f"⚠ Font match failed for episode: {ep_name}"),
    action="Dismiss",
)
page.snack_bar.open = True
page.update()

# Critical: AlertDialog
def show_critical_error(title: str, message: str, suggestion: str):
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(f"{message}\n\n💡 {suggestion}"),
        actions=[ft.TextButton("Dismiss", on_click=lambda e: close_dialog(dialog))],
    )
    page.overlay.append(dialog)
    dialog.open = True
    page.update()
```

---

## R7: Flet Testing Approach

**Decision**: Test GUI components via unit tests of pure logic (messages, log bridge, data transforms) and boundary compliance tests (import auditing). Flet does NOT provide a Pilot/test-runner API like Textual. Widget rendering tests are deferred to manual/integration testing.

**Rationale**: Unlike Textual (which has Pilot API for headless widget testing), Flet has no official testing framework for headless widget interaction. The recommended approach is:
1. **Unit test pure logic**: Message construction, log bridge processor, data transformation functions — these are plain Python, no Flet dependency needed.
2. **Boundary compliance test**: `ast.parse` source files and assert no forbidden imports (adapters, hunters, core) from `src/gui/` except via bootstrap.
3. **Manual integration test**: Launch app and verify visually.

**Alternatives Considered**:
- Flet's experimental `flet.testing` — Not stable/documented enough for production use.
- Selenium/Playwright against Flet web mode — Heavyweight, fragile, overkill for this project.
- Mock `ft.Page` and simulate events — Possible but brittle. Better to keep GUI thin and test logic separately.

**Conclusion**: Keep GUI layer thin (all logic in message transforms and log bridge). Test those thoroughly. Widget tests are N/A for now.

---

## R8: Flet Event Loop Throttling — Batching UI Updates

**Decision**: Use a time-based throttle in the activity feed consumer. The feed's queue consumer runs on a periodic timer (~100ms interval = max 10 updates/sec). Each tick drains all queued entries and batch-appends them to the ListView, then calls `update()` once.

**Rationale**: Flet's `page.update()` sends a diff to the client. Calling it per-log-entry under high-frequency events (e.g., per-font queries) would cause UI lag. Batching into 100ms windows ensures max ~10 rendered updates/second per spec requirement (SC-005).

**Alternatives Considered**:
- `asyncio.sleep()` loop with drain — Works but `page.run_task()` with periodic wakeup is cleaner.
- Debounce (reset timer on each event) — REJECTED. Would delay display of burst events. Throttle (fixed interval) is better for real-time feeds.
- Flet `page.on_idle` callback — Not available / not reliable for periodic work.

**Pattern**:
```python
THROTTLE_INTERVAL_MS = 100  # 10 updates/sec max

async def consume_log_queue(queue: asyncio.Queue, feed: ListView):
    while True:
        await asyncio.sleep(THROTTLE_INTERVAL_MS / 1000)
        entries = []
        while not queue.empty():
            try:
                entries.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if entries:
            for entry in entries:
                feed.controls.append(format_entry(entry))
            feed.update()  # single update for entire batch
```

---

## Summary

All 8 research topics resolved. No NEEDS CLARIFICATION remaining. Key decisions:
- `page.run_task()` for async background pipeline execution
- `asyncio.Queue` log bridge with 100ms throttled consumer
- Built-in Flet widgets (DataTable, FilePicker, ProgressBar/Ring, SnackBar, AlertDialog) — no custom widgets needed
- Unit test pure logic + boundary compliance; no headless widget testing (Flet lacks Pilot API)
