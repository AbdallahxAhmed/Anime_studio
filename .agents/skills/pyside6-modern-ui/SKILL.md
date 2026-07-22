---
name: pyside6-modern-ui
description: Build or polish Anime Studio PySide6 desktop interfaces. Use for PySide6 widget layouts, QSS/themes, desktop interaction design, visual states, high-DPI behavior, and accessible modern UI work; do not use for web, React, Tailwind, browser CSS, or Textual TUI work.
---

# PySide6 modern UI

Keep Anime Studio a native, restrained Windows desktop application. Work in
`src/gui/`; keep business rules, filesystem access, subprocesses, and pipeline
orchestration out of widgets.

## Design workflow

1. Read the existing GUI/theme and relevant widget tests before changing a surface.
2. Add semantic tokens to the central theme source; do not scatter raw colors,
   dimensions, or ad-hoc widget styles.
3. Use the 8px spacing grid: 4, 8, 12, 16, 24, 32. Keep compact controls at
   32px and prominent actions at 36px or 40px.
4. Establish a clear typography hierarchy: application/show title, section
   title, body, and secondary metadata. Prefer the system UI font and honor
   system/high-DPI scaling.
5. Give every control Hover, Pressed, Disabled, and keyboard Focus states.
   Focus must be visible; disabled text must remain readable.

## Desktop interaction rules

- Use text on primary, secondary, and destructive actions. Do not make an
  unexplained icon-only action; every icon has a tooltip and accessible label.
- Make one primary action prominent, keep secondary actions quieter, and give
  Stop/Undo/destructive actions a distinct semantic treatment.
- Provide explicit empty, loading/scanning, processing, stopped, success, and
  error states. Stopped is neutral, never success or failure.
- Set accessible names/descriptions and tooltips. Make dynamic labels such as
  “Run N selected” screen-reader meaningful.
- Set logical tab order and retain Enter/Space button activation and Esc/close
  semantics. Do not rely on color alone for status.
- Elide long show titles and paths rather than clipping them, while exposing the
  full value in a tooltip. Test long English, Arabic, and Japanese text.
- Use Qt layouts, `QSizePolicy`, and token dimensions instead of fixed geometry
  except deliberate surfaces such as the sidebar width.

## Guardrails

- Preserve the GUI/core boundary and existing pipeline behavior during visual
  polish. Do not smuggle business logic into a widget.
- Avoid decorative animation and timing-sensitive behavior.
- Before handing off UI changes, capture and inspect Before/After offscreen
  screenshots and run focused accessibility/GUI tests.
