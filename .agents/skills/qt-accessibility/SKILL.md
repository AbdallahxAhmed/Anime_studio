---
name: qt-accessibility
description: Make Anime Studio PySide6 interfaces accessible and keyboard-operable. Use for accessible names/descriptions, focus order, keyboard interaction, contrast, screen-reader labels, system scaling, and motion/accessibility review; do not use browser accessibility patterns.
---

# Qt accessibility

Treat every interactive widget as usable without a mouse and understandable
without color perception.

## Required checks

- Assign clear `accessibleName`, `accessibleDescription`, and tooltip text to
  actionable controls and meaningful dynamic widgets.
- Define logical Tab order. Verify keyboard-only navigation, visible focus
  rings, Enter/Space activation, and Esc/close behavior.
- Keep screen-reader labels synchronized with dynamic text such as selected
  counts, processing, and stopping state.
- Pair every color-coded status with readable text, a label, or another cue.
  Keep disabled controls readable and target strong text/background contrast.
- Respect system font/high-DPI scaling; test long English, Arabic, and Japanese
  strings without clipping. Prefer semantic Qt labels over custom-drawn text
  when screen readers need the content.
- Avoid unnecessary animation. Honor reduced-motion expectations by keeping
  state transitions immediate and informative.

## Implementation rules

Use native PySide6 widgets and QSS/token roles, not web ARIA/CSS or browser
patterns. Keep accessibly descriptive presentation in `src/gui/`; do not add
business logic to widgets. Add pytest-qt tests for focus, keyboard activation,
names, enabled state, and state transitions when behavior changes.
