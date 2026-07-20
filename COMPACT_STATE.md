# COMPACT_STATE.md — Anime Studio v3

**Last Updated**: 2026-07-21
**Active Branch**: `011-gui-redesign`
**Verified HEAD**: `64f8641abbe366a4e5a0ff92e9272e5b92ef1639` (RECOVERY-R1.1)
**Constitution**: v1.9.0
**Status**: Backend (0–3) ✅ | GUI (5b) ✅ | Font Ingestion (6) ✅ | Font Hunter Chain (6.6) ✅ | Pre-packaging UX (7) ✅ | Pipeline Control (7.5) ✅ | Phase 8a Wave 5 ✅ (Verified) | **Wave 6**: NOT STARTED | **Wave 7**: NOT STARTED | **Tests**: Full collected suite: 313 passed

---

## 🚨 CRITICAL — Read Before Starting Any Session

### Recovery Baseline & Verification

- **RECOVERY-R1**: `679c400f97b6074907f1415e72a7587e36145d02` (restored 109 functional files from working tree).
- **RECOVERY-R1.1**: `64f8641abbe366a4e5a0ff92e9272e5b92ef1639` (formatting-only for `main.py` and `scratch/create_fonts.py` after 100% AST equivalence was proven).
- **Verified Clean-Worktree Gates**:
  - `uv sync --extra dev`: passed
  - `ruff check .`: passed
  - `ruff format --check .`: passed (150 files formatted)
  - `mypy src/ --strict`: passed (0 errors across 75 source files)
  - `pytest --collect-only -q`: 313 tests collected (unit and contract test suite)
  - `pytest -q`: 313 collected tests passed (1 warning)
  - Boundary test (`test_boundary.py`): passed
  - Detached worktree status: clean and reproducible
  - Original working tree status: contains unrelated unstaged local/agent/legacy changes pending hygiene cleanup

### Documented Verification Warning
- `tests/unit/adapters/test_subprocess.py::test_subprocess_timeout[asyncio]`
- `RuntimeWarning`: coroutine `'AsyncMockMixin._execute_mock_call'` was never awaited around `process.kill()`. Tests pass, but marked as technical debt.

---

## 🔄 Repository Recovery History

- **Context**: The previous committed HEAD (`9afd33c`) was not reproducible from a clean checkout because required production modules and tests from Phases 6.6, 7, and 7.5 existed only as untracked/modified files in the local working directory.
- **Action**: Recovery consolidated all functional work into `RECOVERY-R1` (`679c400`). Subsequently, `RECOVERY-R1.1` (`64f8641`) applied strict formatting fixes to `main.py` and `scratch/create_fonts.py` after verifying AST parity.
- **Result**: All quality gates (Ruff lint/format, MyPy strict typing, 313 collected tests, GUI boundary tests) are 100% reproducible from clean detached checkouts.

---

## 🗺️ Project Timeline & GUI Redesign Waves

| Phase / Wave | Status | Notes |
| ------------ | ------ | ----- |
| Phase 0 — Domain Models | ✅ DONE | 28 tests, immutable dataclasses |
| Phase 1 — Core Adapters | ✅ DONE | 58 tests, async-first |
| Phase 2 — Font System | ✅ DONE | 6-layer hunter architecture |
| Phase 3 — Pipeline | ✅ DONE | Semaphore-gated disk I/O, full report |
| Phase 4 — TUI (Textual) | ⚠️ DISCARDED | UI complexity; replaced by PySide6 GUI |
| Phase 5b — PySide6 GUI | ✅ DONE | Thread-safe, qasync integration |
| Phase 6 — Font Ingestion | ✅ DONE | Auto-discovery, import button, drag-drop |
| Phase 6.6 — Font Hunter Chain | ✅ DONE | 10 hunters, 231 tests |
| Phase 7 — Pre-Packaging UX | ✅ DONE | Selective run tree, export logs, `_amux_` temp fix |
| Phase 7.5 — Pipeline Control | ✅ DONE | Smart Stop, Checkpoint, Multi-level Undo |
| **Phase 8a GUI Redesign Wave 1** | ✅ DONE | Domain models — `ShowStatus` and `ShowSummary`, with tests |
| **Phase 8a GUI Redesign Wave 2** | ✅ DONE | New GUI widgets — `ShowSidebarWidget` and `EpisodeTableWidget`, with tests |
| **Phase 8a GUI Redesign Wave 3** | ✅ DONE | Core indexing/scanning — `ShowIndexManager` and `LibraryScanner.scan_folder()`, with tests |
| **Phase 8a GUI Redesign Wave 4** | ✅ DONE | Modify widgets — collapsible `ActivityFeedWidget` and simplified `ProgressPanelWidget` |
| **Phase 8a GUI Redesign Wave 5** | ✅ DONE | `MainWindow` & `bootstrap.py` rewrite, explicit Refresh, Stop/Undo/closeEvent/drag-drop preservation, full-path `EpisodeResult` contract, regression tests |
| **Phase 8a GUI Redesign Wave 6** | 📋 NOT STARTED | Remove legacy `selection_tree.py` and `library_picker.py` only after approval |
| **Phase 8a GUI Redesign Wave 7** | 📋 NOT STARTED | Final verification and real GUI/E2E checks |
| Phase 8b — Packaging (.exe) | 📋 PLANNED | PyInstaller spec for Windows .exe |
| Phase 9 — Settings UI | 📋 PLANNED | Visual config.toml editor + QDialog |
| Phase 10 — Subtitle Downloader | 📋 PLANNED | SubDL API — deferred to v3.1 |

---

## ✅ Verified Complete Capabilities

### Backend (Phases 0–7.5) & GUI Redesign Waves 1–5 — STABLE & VERIFIED
- **Domain Models** (`src/models/`): `Episode`, `SubtitleFile`, `FontAsset`, `MuxResult`, `RunManifest`, `PipelineCheckpoint`, `ShowStatus`, `ShowSummary`.
- **Core Services** (`src/core/`): `PipelineRunner`, `FontResolver`, `FontIngestionService`, `CheckpointManager`, `UndoService`, `LogExport`, `ShowIndexManager`, `LibraryScanner`.
- **10 Font Hunters** (`src/hunters/`): Layer 0 (FontCache), Layer 1 (MkvExtractHunter), Layer 2 (SiblingFontHunter), Layer 3 (SystemFontHunter), Layer 4 (GoogleFonts, FontSquirrel, DaFont, FontSpace, BeFonts, ArabicFonts), Layer 5 (SearchEngineHunter).
- **GUI & Redesign** (`src/gui/`): PySide6 + qasync. Redesign Waves 1–5 implemented with `ShowSidebarWidget`, `EpisodeTableWidget`, collapsible `ActivityFeedWidget`, simplified `ProgressPanelWidget`, encapsulated sidebar refresh, and full-path `EpisodeResult.episode_path` contract.
- **Test Suite**: 313 collected tests passed (unit and contract tests). Real-binary integration verification remains a separate open gate.

---

## 🔴 KNOWN GAPS & TECHNICAL DEBT

1. **Known AsyncMock RuntimeWarning**: `tests/unit/adapters/test_subprocess.py::test_subprocess_timeout[asyncio]` produces unawaited coroutine warning on `process.kill()`.
2. **Broad `except Exception` Debt**: Approximately 43 sites outside Wave 5 contain broad exception handling, requiring per-site audit.
3. **Integration/Contract Verification**: External integration test suites require separate verification with real MKV fixtures.
4. **Episode Pairing Substring Bug**: Episode pairing involving `.7.` substring remains unresolved.
5. **Extracted Font Corruption**: `Times New Roman Bold.ttf` extracted at 101 bytes remains unresolved.
6. **MkvExtractHunter Performance**: First-run unindexed scan performance debt remains unresolved.
7. **Dependency Check UI**: Startup warnings print to console; visual `QMessageBox` critical modal missing.
8. **ots-sanitize Integration**: Not wired into font repair pipeline.
9. **alass Integration**: `alass` installation and primary path fallback logic unresolved.
10. **Documentation & Packaging**: User-facing README and PyInstaller `.exe` specification not built.
11. **Subtitle Downloader**: SubDL API integration deferred to post-v3.0.
12. **Original Working Tree Hygiene**: The original working directory contains unrelated unstaged local modifications (`.specify/feature.json`, `AGENTS.md`, `Anime_Studio.py`, `main.py`, `scratch/`) pending a separate cleanup decision. (Only detached worktrees are clean).

---

## 🏗️ Architecture Rules (Constitution v1.9.0)

### Hexagonal Layer Restrictions (STRICT)
```
models/   → imports NOTHING from this project
ports/    → imports models/ only
core/     → imports models/, ports/ only
hunters/  → imports models/, ports/ only
adapters/ → imports models/, ports/ only
gui/      → imports core/, models/ only via bootstrap.py
```

### Font Resolution Layering
```
[0] LocalCache       → .anime_studio/font_cache/
[1] MkvExtract       → embedded fonts from MKVs
[2] SiblingScan      → Fonts/ dirs adjacent to episodes
[3] SystemFontHunter → OS font dirs (C:\Windows\Fonts, etc.)
[4] NetworkHunters   → Google Fonts, FontSquirrel, DaFont, etc.
[5] SearchEngine     → DuckDuckGo HTML search fallback
```

---

## 💾 Storage Layout

```
C: (VOLATILE):
  %APPDATA%\AnimeStudio\config.toml

D: (PERMANENT):
  D:\Entertainment\.anime_studio\
  ├── font_cache\
  ├── font_library.toml
  ├── pipeline_checkpoint.toml
  ├── run_history\
  └── logs\
  D:\Entertainment\.anime_studio_trash\
```

---

**End of COMPACT_STATE.md**
