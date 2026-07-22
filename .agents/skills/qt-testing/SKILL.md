---
name: qt-testing
description: Write deterministic Anime Studio PySide6 tests with pytest-qt and qasync. Use for widget interaction, signals, focus/keyboard behavior, state transitions, cancellation, visual geometry checks, and GUI/core integration tests; do not use timing sleeps or real-media pipelines.
---

# Qt testing

Use `pytest-qt` for real widget interaction and `pytest-asyncio`/qasync-aware
tests for application coroutines. Keep tests deterministic and isolated.

## Test patterns

- Use `qtbot.addWidget`, `mouseClick`, `keyClick`, `waitSignal`, and focused
  assertions for controls, signals, Tab order, and Enter/Space behavior.
- Coordinate async flow with `asyncio.Event`, controlled Futures, and signal
  waits. Never add timing sleeps.
- Test enabled/disabled, accessible name/description, focus visibility,
  selection counts, and stopped/error/success/empty state explicitly.
- Use `tmp_path`, fake empty media, and mocked subprocess/filesystem boundaries.
  Do not use the real anime library or run a real-media pipeline.
- Exercise cancellation before/during bounded work; assert no later batch,
  neutral stopped result, task cleanup, and no un-retrieved exceptions.
- Keep geometry/screenshot regressions lightweight: assert layout constraints
  in tests and create local offscreen review artifacts separately.

## Suite structure

Keep unit tests local to widgets/models, integration tests on real composition
paths, and manual visual review separate. Use pywinauto only for explicitly
optional Windows smoke tests; portable tests must not require it. End GUI tests
with owned-task/warning checks and clean widget teardown.
