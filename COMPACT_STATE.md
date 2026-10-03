# COMPACT_STATE.md — Anime Studio v3

**Last Updated**: 2026-10-03
**Active Branch**: `main`
**HEAD**: `eca56b5`
**Constitution**: v1.9.0
**Status**: Feature 013 & Embedded Pipeline COMPLETE — MERGED & PUSHED TO MAIN ✅ | 820 tests passed | Ruff, format, mypy --strict passed | Live media verified

---

## 🚨 CRITICAL — Read Before Starting Any Session

### Production Baseline

- **Human Verdict**: PHASE 8 + FEATURE 013 MERGED TO MAIN
- **Branch**: `main`
- **HEAD**: `eca56b5`
- **Automated Baseline**:
  - Python 3.11.9
  - 820 tests passed
  - `ruff check .` passed
  - `ruff format --check .` passed
  - `mypy --strict` passed across 81 source files
- **Live Verification**:
  - *Serial Experiments Lain*: 13/13 episodes with embedded `und` subtitles extracted, synced with `alass`, fonts resolved (10/10), and remuxed with `mkvmerge` (clean undo backup preserved).

### Documented Verification Warning
- `tests/unit/adapters/test_subprocess.py::test_subprocess_timeout[asyncio]`
- `RuntimeWarning`: coroutine `'AsyncMockMixin._execute_mock_call'` was never awaited around `process.kill()`. Tests pass; known pre-existing technical debt.

---

## 🔄 Repository Recovery History

- **Context**: The previous committed HEAD (`9afd33c`) was not reproducible from a clean checkout because required production modules and tests from Phases 6.6, 7, and 7.5 existed only as untracked/modified files in the local working directory.
- **Action**: Recovery consolidated all functional work into `RECOVERY-R1` (`679c400`). Subsequently, `RECOVERY-R1.1` (`64f8641`) applied strict formatting fixes to `main.py` and `scratch/create_fonts.py` after verifying AST parity.
- **Result**: All quality gates (Ruff lint/format, MyPy strict typing, tests, GUI boundary tests) are 100% reproducible from clean detached checkouts.

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
| **Phase 8a GUI Redesign** | ✅ DONE | Waves 1–7 complete: two-panel layout, sidebar, episode table, responsive feed |
| **Feature 013 — Renderability Engine** | ✅ DONE | 374 new tests: libass-compatible font coverage, OpenType cmap, fallback selection |
| **Feature 013+ — Embedded Subtitles** | ✅ DONE | Embedded ASS extraction, track selection, deduplicated muxing, folder scan caching |
| Phase 8b — Packaging (.exe) | 📋 PLANNED | PyInstaller spec for Windows .exe |
| Phase 9 — Settings UI | 📋 PLANNED | Visual config.toml editor + QDialog |
| Phase 10 — Subtitle Downloader | 📋 PLANNED | SubDL API — deferred to v3.1 |

---

## ✅ Verified Complete Capabilities

### Backend (Phases 0–7.5) & GUI Redesign Waves 1–7 — COMPLETE & HUMAN-APPROVED
- **Domain Models** (`src/models/`): `Episode`, `SubtitleFile`, `FontAsset`, `MuxResult`, `RunManifest`, `PipelineCheckpoint`, `ShowStatus`, `ShowSummary`.
- **Core Services** (`src/core/`): `PipelineRunner`, `FontResolver`, `FontIngestionService`, `CheckpointManager`, `UndoService`, `LogExport`, `ShowIndexManager`, `LibraryScanner`.
- **10 Font Hunters** (`src/hunters/`): Layer 0 (FontCache), Layer 1 (MkvExtractHunter), Layer 2 (SiblingFontHunter), Layer 3 (SystemFontHunter), Layer 4 (GoogleFonts, FontSquirrel, DaFont, FontSpace, BeFonts, ArabicFonts), Layer 5 (SearchEngineHunter).
- **GUI & Redesign** (`src/gui/`): PySide6 + qasync. Redesign Waves 1–7 complete with `ShowSidebarWidget`, `EpisodeTableWidget`, collapsible `ActivityFeedWidget`, simplified `ProgressPanelWidget`, encapsulated sidebar refresh, full-path `EpisodeResult.episode_path` contract, legacy widgets removed.
- **Test Suite**: 386 tests passed (unit and contract tests). Real-binary integration verification remains a separate open gate.

---

## 🔴 KNOWN GAPS & TECHNICAL DEBT

1. **Exported Log Timestamps**: Mix UTC structured events with Cairo-local GUI events.
2. **Known AsyncMock RuntimeWarning**: `src/adapters/subprocess.py:60` — coroutine `'AsyncMockMixin._execute_mock_call'` was never awaited.
3. **Sidebar UX Polish**: Horizontal scrollbar/title elision and technical Activity Log labels.
4. **Incremental Large-Library Performance**: Refresh/index performance for large libraries.
5. **Stale Cached Data**: Safely remove stale cached "Anime — 592 episodes" later; never by deleting the whole cache blindly.
6. **Episode Pairing Bug**: Episode `.7.` fuzzy-pairing substring bug unresolved.
7. **Extracted Font Corruption**: 101-byte extracted-font corruption investigation pending.
8. **Broader Real-Binary Coverage**: Integration test suites require separate verification with real MKV fixtures.
9. **Broad `except Exception` Cleanup**: Approximately 43 sites outside Wave 5 contain broad exception handling.
10. **Dependency Check UI**: Startup warnings print to console; visual `QMessageBox` critical modal missing.
11. **ots-sanitize Integration**: Not wired into font repair pipeline; alass installation/path decision pending.
12. **Documentation & Packaging**: README, PyInstaller `.exe` specification, and subtitle downloader not built.

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
