---
name: qt-visual-review
description: Review Anime Studio PySide6 visual quality with reproducible offscreen screenshots and evidence-based acceptance checks. Use for desktop layout changes, visual regressions, theme work, high-DPI review, and UI-state review; do not use web-browser visual workflows.
---

# Qt visual review

Generate local, untracked/off-repository review artifacts. Visual review is
evidence for manual inspection, not a claim of human approval.

## Screenshot matrix

Capture each relevant view at 1280×720 and 1920×1080. Use 100%, 125%, and 150%
scale where practical, with a fresh offscreen process per scale.

Include these states:

- empty/no-show state;
- loaded show and long title/path;
- scanning or processing;
- stopped, complete, and error;
- sidebar, episode table, progress panel, and activity log collapsed/expanded;
- long English, Arabic, and Japanese strings; and
- scrollbar and selected/focused control behavior.

## Review checklist

- Check clipping, alignment, whitespace, density, control height, and table
  column behavior at each viewport and scale.
- Check contrast for text, status badges, disabled controls, focus rings, and
  hover/pressed states. Status must have text or another non-color cue.
- Check sidebar rows, table headers/checkboxes, progress and activity states,
  long text elision plus tooltip, and no unexpected scrollbars.
- Compare before/after only against the stated product goals. Record artifact
  paths and an evidence-based pass/fail matrix; identify items requiring human
  sign-off instead of inventing approval.

## Safety

Use fake data, `tmp_path`, and mocked binary boundaries. Do not launch the real
anime library or commit screenshots unless repository policy requires it.
