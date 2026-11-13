# Anime Studio desktop app

Tauri 2 shell + Svelte 5 UI on top of the existing Python core.

```
┌──────────── Tauri window (native menu, dialogs) ────────────┐
│  Svelte UI  ── invoke("backend_send") ──►  Rust (src-tauri)  │
│             ◄── event "backend://message" ──                 │
└──────────────────────────────┬──────────────────────────────┘
                               │ JSON-RPC 2.0, one JSON per line
                               ▼
              Python backend: python -m src.sidecar
              (PipelineRunner, UndoService, scanner, hunters)
```

Rust only starts the backend and relays lines; all logic stays in Python.

## Requirements

- Node 20+ and Rust (stable) — https://tauri.app/start/prerequisites/
- Linux: `webkit2gtk-4.1` (Arch: `sudo pacman -S webkit2gtk-4.1`)
- MKVToolNix and FFmpeg on the PATH (the app tells you if they are missing)
- Python environment for the backend: `uv sync` in the repository root

## Develop

```bash
cd desktop
npm install

# UI only, in a browser, with a built-in fake backend:
npm run dev            # http://localhost:1420  (?demo=apply|run|history|setup)

# Real app with the Python backend from this checkout:
export ANIME_STUDIO_BACKEND_DIR="$(cd .. && pwd)"
export ANIME_STUDIO_PYTHON="$ANIME_STUDIO_BACKEND_DIR/.venv/bin/python"   # Windows: .venv\Scripts\python.exe
npx tauri dev
```

## Build an installer

```bash
# 1. Freeze the backend into a single executable (name matches Tauri's externalBin)
cd .. && uv run --with pyinstaller python scripts/build_sidecar.py
# 2. Build the app and installers (.msi/.exe on Windows, .deb/.rpm/.AppImage on Linux)
cd desktop && npx tauri build
```

## Checks

```bash
npm run check   # svelte-check, TypeScript strict
npm run build   # production bundle
```

## Keyboard

| Key | Action |
| --- | --- |
| Ctrl+Enter | Apply to selected episodes |
| Space | Select / unselect the focused episode |
| ↑ ↓ (or J K) | Move between episodes |
| F5 | Rescan |
| Ctrl+H | History and undo |
| Ctrl+, | Preferences |
