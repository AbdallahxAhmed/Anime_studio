# Feature Specification: Standalone Windows Packaging (.exe)

**Feature ID**: `014-packaging-exe`  
**Phase**: Phase 8b  
**Status**: Implemented & Verified ✅  
**Target Platform**: Windows 10/11 x64  

---

## 1. Problem Statement

Previously, Anime Studio could only be launched from a developer environment by executing `uv run python -m src` with Python 3.11 and all virtualenv dependencies installed. Non-technical users or users on systems without Python/`uv` could not run the application directly.

To distribute Anime Studio as a standalone desktop application, we need an automated packaging pipeline that builds a standalone Windows executable (`AnimeStudio.exe`) bundled with:
1. Python runtime and all compiled extensions (`PySide6`, `qasync`, `pydantic_core`, `fontTools`, `httpx`).
2. Centralized dark styling assets and fonts.
3. Dynamic plugin architecture (all 82 internal modules discovered via `bootstrap.py`).
4. Automatic portable external tool discovery (`ffmpeg`, `mkvmerge`, `mkvextract`, `alass`) inside an adjacent `tools/` folder.

---

## 2. Requirements

### Functional Requirements
- **FR-001**: Provide a canonical `AnimeStudio.spec` PyInstaller configuration that packages the complete application into `dist/AnimeStudio/AnimeStudio.exe`.
- **FR-002**: Ensure all dynamic imports loaded via `importlib.import_module()` in `bootstrap.py` (all core forensic modules, font hunters, adapters, GUI widgets) are collected and bundled into the frozen binary.
- **FR-003**: Provide a clean `--smoke-test` and `--version` CLI flag in `src/__main__.py` to allow headless verification of the packaged binary.
- **FR-004**: Support portable external tools: `DependencyChecker` must scan `tools/` adjacent to `AnimeStudio.exe` for `ffmpeg.exe`, `mkvmerge.exe`, `mkvextract.exe`, and `alass.bat` before falling back to system paths.
- **FR-005**: Provide an automated build script `scripts/build_exe.py` that cleans, builds, creates portable directory structure, and runs smoke test verification.

### Non-Functional Requirements
- **NFR-001 (Startup Performance)**: Use `onedir` distribution mode to avoid the 5–10s extraction overhead of `onefile` decompression on every launch.
- **NFR-002 (Size Optimization)**: Exclude heavy unused packages (`tkinter`, `matplotlib`, `scipy`, `pandas`, `IPython`) to keep the distribution around ~130 MB.
- **NFR-003 (Zero Regressions)**: Packaging modifications must not break existing test suites (`pytest` 820 passing tests, `ruff`, `mypy --strict`).
