# Implementation Plan: Standalone Windows Packaging (.exe)

**Feature**: `014-packaging-exe` | **Phase**: Phase 8b | **Date**: 2026-10-03  

---

## 1. Technical Context

- **Build System**: PyInstaller 6.22+ via `uv add --dev pyinstaller`
- **Application Framework**: PySide6 6.7+ with `qasync` event loop
- **Architecture**: Hexagonal architecture with dynamic service instantiation in `src/gui/bootstrap.py`
- **Target OS**: Windows 10/11 64-bit

---

## 2. Architecture & Design Decisions

### Decision 1: `onedir` Mode for Instant Startup
PySide6 contains >120 MB of Qt binaries (`Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll`, etc.). In `onefile` mode, Windows must decompress the entire archive into `%TEMP%\_MEIxxxxxx` on every launch, causing a 5-10s delay. `onedir` mode extracts once at build time into `dist/AnimeStudio/`, achieving instantaneous sub-second application launch.

### Decision 2: Automated Hidden Import Collection
Because `bootstrap.py` uses dynamic `importlib.import_module()` to maintain strict Hexagonal layer separation, standard static analysis misses dynamically loaded modules. The spec file uses `collect_submodules("src")` to dynamically collect all 82 modules across `src.adapters`, `src.core`, `src.hunters`, `src.gui`, and `src.models`.

### Decision 3: Portable Tool Directory
`DependencyChecker.discover_one()` was enhanced with Step 0 to look inside an adjacent `tools/` folder. This enables truly portable distributions where `mkvmerge.exe` and `ffmpeg.exe` can be placed alongside `AnimeStudio.exe`.

---

## 3. Implemented Components

| Component | Path | Description |
|---|---|---|
| **Spec File** | `AnimeStudio.spec` | Canonical PyInstaller configuration with submodules, data files, and excludes |
| **CLI Flags** | `src/__main__.py` | `--version` and `--smoke-test` for headless verification |
| **Tool Discovery** | `src/adapters/dependency_checker.py` | Step 0 discovery checking adjacent `tools/` directory |
| **Build Script** | `scripts/build_exe.py` | Automated build, directory preparation, and smoke testing |

---

## 4. Verification

- **Compilation**: Successfully compiled `dist/AnimeStudio/AnimeStudio.exe` (129.7 MB) in 64.1s.
- **Headless Smoke Test**: `AnimeStudio.exe --smoke-test` exited with code 0 (`Anime Studio smoke test: OK`).
- **Version Flag**: `AnimeStudio.exe --version` exited with code 0 (`Anime Studio v3.0.0`).
- **Regression Testing**: All 820 pytest tests pass, `ruff check` passes, `mypy --strict` passes.
