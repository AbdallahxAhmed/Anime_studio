# Tasks: Complete Font Hunter Chain (Phase 6.6)

**Input**: Design documents from `specs/008-font-hunter-chain/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md

**Tests**: Included — each hunter gets a test file immediately after implementation.

**Organization**: Tasks ordered by strict dependency chain: foundation → local hunters → network hunters → nuclear option → integration → cleanup.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory structure and shared utilities required by all hunters

- [ ] T001 Create `src/hunters/sources/__init__.py` with empty exports
- [ ] T002 Create shared font verification utilities in `src/hunters/sources/_hunter_utils.py` — include `verify_font()`, `extract_fonts_from_zip()`, `normalize_font_name()`, `font_name_matches()` functions using fontTools. See plan.md Component 1 for exact signatures.
- [ ] T003 [P] Write unit tests for `_hunter_utils` in `tests/unit/hunters/sources/test_hunter_utils.py` — test `verify_font()` with valid/corrupt data, `extract_fonts_from_zip()` with real ZIP, `font_name_matches()` normalization

**Constitution constraints**: fontTools for verification (§XI), no new dependencies.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Fix priority numbering before any registration. MUST complete before user story phases.

**⚠️ CRITICAL**: No hunter registration can happen until priority is correct.

- [ ] T004 [US5] Fix `SystemFontHunter.priority` from `4` to `3` in `src/hunters/system_font_hunter.py` line 107. Update any tests that assert `priority == 4` to expect `3`.
- [ ] T005 [US2] Search and confirm zero FuzzyMatchHunter code exists in `src/`. Grep for `FuzzyMatch` in `src/` — if any hunter class found, delete it. Document: the library scanner's fuzzy episode-subtitle pairing (`src/core/library_scanner.py` lines 300, 328) is UNRELATED and must NOT be touched.

**Checkpoint**: SystemFontHunter priority correct. No FuzzyMatch hunter code exists. Ready for new hunter implementation.

---

## Phase 3: User Story 5 — Layers 1 & 2 Registration (Priority: P1) 🎯 MVP

**Goal**: Local font hunters that resolve fonts without network access

**Independent Test**: Place `.ttf` files in a `Fonts/` dir next to episodes. Verify SiblingFontHunter resolves them. For MkvExtractHunter, use an MKV with embedded font attachments.

### Implementation for Layers 1 & 2

- [ ] T006 [US5] Implement `SiblingFontHunter` in `src/hunters/sources/sibling_font.py` — scan `Fonts/`, `fonts/`, `Font/`, `font/` dirs adjacent to episode AND parent dir. Use `asyncio.to_thread()` for dir scanning. fontTools nameID matching via `_hunter_utils`. `priority=2`, `rate_limit=0.0`, `ping_url=None`, `is_cacheable=True`. Return `FontPayload` with font bytes from file read. See plan.md Component 3.
  - **Depends on**: T001, T002
  - **Constitution**: §III async-first (asyncio.to_thread for filesystem), §V HunterProtocol

- [ ] T007 [P] [US5] Write unit tests for `SiblingFontHunter` in `tests/unit/hunters/sources/test_sibling_font.py` — test: finds font in adjacent `Fonts/` dir, finds font in parent `Fonts/` dir, returns empty when no match, returns empty when no `Fonts/` dir exists, fontTools verification rejects corrupt file, `supports()` returns True
  - **Depends on**: T006

- [ ] T008 [US5] Implement `MkvExtractHunter` in `src/hunters/sources/mkv_extract.py` — accept `SubprocessPort` and optional `library_path: Path`. On first `search()`, scan all `.mkv` files via `mkvmerge -J` to index font attachments (lazy, one-time). Extract fonts via `mkvextract attachments <mkv> <id>:<temp>`. Verify with fontTools. `priority=1`, `rate_limit=0.0`, `ping_url=None`, `is_cacheable=True`. See plan.md Component 2.
  - **Depends on**: T001, T002
  - **Constitution**: §III async-first (subprocess), §VII subprocess lifecycle (timeout), §I hexagonal (SubprocessPort, not adapter)

- [ ] T009 [P] [US5] Write unit tests for `MkvExtractHunter` in `tests/unit/hunters/sources/test_mkv_extract.py` — mock `SubprocessPort`, test: `mkvmerge -J` returns attachment list, `mkvextract attachments` extracts font, font verified by fontTools, returns empty when no attachments, handles subprocess failure gracefully, lazy indexing (only scans once)
  - **Depends on**: T008

**Checkpoint**: Local font resolution works — `SiblingFontHunter` and `MkvExtractHunter` resolve fonts from filesystem without network.

---

## Phase 4: User Story 3 — Layer 4 Known Font Repositories (Priority: P1)

**Goal**: Network hunters for the 6 major free font repositories

**Independent Test**: With cache empty, resolve "Open Sans" → GoogleFontsHunter downloads it. Resolve "Bleeding Cowboys" → DaFontHunter or FontSpaceHunter finds it.

### Implementation for Layer 4

- [ ] T010 [US3] Implement `GoogleFontsHunter` in `src/hunters/sources/google_fonts.py` — download ZIP from `https://fonts.google.com/download?family={name}`. Extract ZIP via `_hunter_utils.extract_fonts_from_zip()`. Match requested name against extracted fonts via `font_name_matches()`. Accept `proxy: str | None` for httpx. `priority=4`, `rate_limit=0.5`, `circuit_breaker_threshold=3`, `ping_url="https://fonts.google.com"`. See plan.md Component 4.
  - **Depends on**: T001, T002
  - **Constitution**: §III httpx async only, §V HunterProtocol, proxy from config (§III)

- [ ] T011 [P] [US3] Write unit tests for `GoogleFontsHunter` in `tests/unit/hunters/sources/test_google_fonts.py` — mock httpx responses, test: successful ZIP download + extraction, 404 returns empty list, corrupt ZIP returns empty, network timeout raises exception (circuit breaker records failure), proxy parameter passed to httpx client
  - **Depends on**: T010

- [ ] T012 [P] [US3] Implement `FontSquirrelHunter` in `src/hunters/sources/fontsquirrel.py` — search `https://www.fontsquirrel.com/fonts/list/find_fonts?q={name}`, parse HTML for font slug, download ZIP from `https://www.fontsquirrel.com/fonts/download/{slug}`. `priority=4`, `rate_limit=1.0`, `ping_url="https://www.fontsquirrel.com"`. See plan.md Component 5.
  - **Depends on**: T001, T002
  - **Constitution**: §III httpx async, §V HunterProtocol

- [ ] T013 [P] [US3] Write unit tests for `FontSquirrelHunter` in `tests/unit/hunters/sources/test_fontsquirrel.py`
  - **Depends on**: T012

- [ ] T014 [P] [US3] Implement `DaFontHunter` in `src/hunters/sources/dafont.py` — search `https://www.dafont.com/search.php?q={name}`, parse HTML for font page link, download font archive. `priority=4`, `rate_limit=1.0`, `ping_url="https://www.dafont.com"`. See plan.md Component 6.
  - **Depends on**: T001, T002

- [ ] T015 [P] [US3] Write unit tests for `DaFontHunter` in `tests/unit/hunters/sources/test_dafont.py`
  - **Depends on**: T014

- [ ] T016 [P] [US3] Implement `FontSpaceHunter` in `src/hunters/sources/fontspace.py` — search `https://www.fontspace.com/search?q={name}`, parse HTML. `priority=4`, `rate_limit=1.0`, `ping_url="https://www.fontspace.com"`. See plan.md Component 7.
  - **Depends on**: T001, T002

- [ ] T017 [P] [US3] Write unit tests for `FontSpaceHunter` in `tests/unit/hunters/sources/test_fontspace.py`
  - **Depends on**: T016

- [ ] T018 [P] [US3] Implement `BeFontsHunter` in `src/hunters/sources/befonts.py` — search `https://befonts.com/?s={name}`, parse HTML. `priority=4`, `rate_limit=1.0`, `ping_url="https://befonts.com"`. See plan.md Component 8.
  - **Depends on**: T001, T002

- [ ] T019 [P] [US3] Write unit tests for `BeFontsHunter` in `tests/unit/hunters/sources/test_befonts.py`
  - **Depends on**: T018

- [ ] T020 [P] [US3] Implement `ArabicFontsHunter` in `src/hunters/sources/arabic_fonts.py` — search `https://arbfonts.com/` for Arabic-script fonts. `priority=4`, `rate_limit=1.0`, `ping_url="https://arbfonts.com"`. See plan.md Component 9.
  - **Depends on**: T001, T002

- [ ] T021 [P] [US3] Write unit tests for `ArabicFontsHunter` in `tests/unit/hunters/sources/test_arabic_fonts.py`
  - **Depends on**: T020

**Checkpoint**: All Layer 4 repository hunters implemented and tested. Google Fonts, FontSquirrel, DaFont, FontSpace, Befonts, ArabicFonts — each with independent circuit breaker and rate limiting.

---

## Phase 5: User Story 4 — Layer 5 SearchEngineHunter (Priority: P2)

**Goal**: DuckDuckGo HTML search as nuclear last-resort option

**Independent Test**: With all Layer 4 hunters returning empty, SearchEngineHunter queries DuckDuckGo and resolves a font from a third-party download page.

### Implementation for Layer 5

- [ ] T022 [US4] Implement `SearchEngineHunter` in `src/hunters/sources/search_engine.py` — query `https://html.duckduckgo.com/html/?q={name}+font+free+download+ttf`. Parse HTML for result links (top 10). For each non-blocked-domain result: fetch page HTML, find direct `.ttf`/`.otf`/`.ttc`/`.zip` download links via URL pattern matching, download candidate, verify with fontTools via `_hunter_utils.verify_font()`. Include `BLOCKED_DOMAINS` frozenset. `priority=5`, `rate_limit=2.0`, `circuit_breaker_threshold=3`, `ping_url="https://html.duckduckgo.com"`. Accept `proxy: str | None`. See plan.md Component 10.
  - **Depends on**: T001, T002
  - **Constitution**: §III httpx async, §V HunterProtocol, proxy from config, asyncio.sleep() rate limiting (never time.sleep)

- [ ] T023 [P] [US4] Write unit tests for `SearchEngineHunter` in `tests/unit/hunters/sources/test_search_engine.py` — mock httpx, test: DuckDuckGo HTML parsed correctly, blocked domains filtered, direct .ttf link found on result page, ZIP download with font extraction, all 10 results exhausted returns empty, corrupt font rejected, rate_limit=2.0 respected
  - **Depends on**: T022

**Checkpoint**: Full 5-layer resolution chain implemented (cache handled by FontResolver, not a hunter). SearchEngineHunter is nuclear last resort before giving up.

---

## Phase 6: User Story 1 — Full Chain Integration (Priority: P1)

**Goal**: Register ALL hunters in bootstrap.py, update error messages, wire complete chain

**Independent Test**: Run full pipeline against anime folder. `mkvinfo output.mkv` shows font attachments. Structlog output shows layer-by-layer resolution trail.

### Integration Tasks

- [ ] T024 [US1] Update `src/hunters/__init__.py` to export all new hunter classes from `src/hunters/sources/`
  - **Depends on**: T006, T008, T010, T012, T014, T016, T018, T020, T022

- [ ] T025 [US1] Register ALL hunters in `src/gui/bootstrap.py` — use `importlib.import_module()` pattern (consistent with existing style). Registration order by priority: MkvExtractHunter(subprocess_adapter, library_path), SiblingFontHunter(), SystemFontHunter() [already registered], GoogleFontsHunter(proxy=config.proxy), FontSquirrelHunter(proxy=config.proxy), DaFontHunter(proxy=config.proxy), FontSpaceHunter(proxy=config.proxy), BeFontsHunter(proxy=config.proxy), ArabicFontsHunter(proxy=config.proxy), SearchEngineHunter(proxy=config.proxy). MkvExtractHunter needs `subprocess_adapter` and `library_path` (from config). Network hunters need `proxy` from config. See plan.md Component 13.
  - **Depends on**: T024, T004
  - **Constitution**: §I hexagonal (dynamic imports in bootstrap), §V plugin registry (all registered, no hardcoding)

- [ ] T026 [US1] Update error message in `src/core/font_resolver.py` line 96 — change from `"Font '{name}' resolution failed after checking all layers. Audit trail: ..."` to `"Font '{name}' not found on any known source. Mux will proceed without this font."`. Keep audit trail in structlog ERROR but not in exception message. See plan.md Component 12, spec FR-011.
  - **Depends on**: None (can run in parallel with other integration tasks)

- [ ] T027 [P] [US1] Write integration-style unit test in `tests/unit/hunters/test_full_chain.py` — create HunterRegistry, register all hunters (with mocks), verify `iter_hunters()` returns them in ascending priority order (1→2→3→4→4→4→4→4→4→5), verify circuit breaker isolation (tripping one hunter doesn't affect others)
  - **Depends on**: T024, T025

**Checkpoint**: Full resolution chain operational — fonts resolved through cache → MKV extract → sibling scan → system fonts → 6 repositories → search engine. Error message matches spec FR-011.

---

## Phase 7: User Story 2 — FuzzyMatch Removal Verification (Priority: P1)

**Goal**: Confirm zero fuzzy font matching in codebase

- [ ] T028 [US2] Remove FuzzyMatch references from `COMPACT_STATE.md` — update lines 73 and 305. Replace Layer 5 description from `"Fuzzy matching fallback"` to `"SearchEngine → DuckDuckGo HTML search (nuclear option)"`. Update layer diagram to show all 6 layers correctly. See plan.md Component 14.
  - **Depends on**: T005

- [ ] T029 [P] [US2] Verify: grep entire `src/` for any fuzzy font matching logic (NOT library scanner episode pairing). Confirm zero hits for `FuzzyMatchHunter`, `Levenshtein`, `fuzz`, `difflib` in context of font resolution. Document in a comment at top of `src/hunters/sources/__init__.py`: `# NOTE: FuzzyMatchHunter intentionally removed (Phase 6.6). Exact match only.`
  - **Depends on**: T005

**Checkpoint**: SC-006 verified — zero occurrences of fuzzy/approximate font matching.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup and validation

- [ ] T030 Run `ruff check src/hunters/sources/` — fix any linting issues in new files
  - **Depends on**: All implementation tasks

- [ ] T031 Run `ruff format src/hunters/sources/` — format all new files
  - **Depends on**: T030

- [ ] T032 Run `pytest tests/unit/ -v --tb=short` — confirm all existing 178+ tests still pass plus new hunter tests
  - **Depends on**: All test tasks

- [ ] T033 [P] Update `src/hunters/__init__.py` `__all__` list to include all new hunter classes
  - **Depends on**: T024

- [ ] T034 Verify `FontAsset.layer_found` field `le=6` constraint works for all layer values (0–5). If Layer 5 = SearchEngine uses `priority=5` but the model has `le=6`, confirm no conflict.
  - **Depends on**: T025

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)         → no deps, start immediately
Phase 2 (Foundational)  → depends on Phase 1
Phase 3 (Layers 1 & 2)  → depends on Phase 1 (T001, T002)
Phase 4 (Layer 4)       → depends on Phase 1 (T001, T002)
Phase 5 (Layer 5)       → depends on Phase 1 (T001, T002)
Phase 6 (Integration)   → depends on ALL hunter implementations (T006–T022)
Phase 7 (FuzzyMatch)    → depends on T005 only
Phase 8 (Polish)        → depends on all previous phases
```

### Critical Path

```
T001 → T002 → T006 (SiblingFont) → T024 → T025 (bootstrap) → T032 (verify)
                 ↘ T008 (MkvExtract) ↗
                 ↘ T010 (GoogleFonts) ↗
                 ↘ T022 (SearchEngine) ↗
```

### Parallel Opportunities

**After T001+T002 complete**, these can ALL run in parallel:
- T006 (SiblingFontHunter) + T007 (tests)
- T008 (MkvExtractHunter) + T009 (tests)
- T010 (GoogleFontsHunter) + T011 (tests)
- T012 (FontSquirrelHunter) + T013 (tests)
- T014 (DaFontHunter) + T015 (tests)
- T016 (FontSpaceHunter) + T017 (tests)
- T018 (BeFontsHunter) + T019 (tests)
- T020 (ArabicFontsHunter) + T021 (tests)
- T022 (SearchEngineHunter) + T023 (tests)

All 9 hunters are independent of each other — they only share `_hunter_utils.py`.

---

## Parallel Example: Layer 4 Hunters

```bash
# After T001 + T002 complete, launch ALL Layer 4 hunters in parallel:
Task T010: "GoogleFontsHunter in src/hunters/sources/google_fonts.py"
Task T012: "FontSquirrelHunter in src/hunters/sources/fontsquirrel.py"
Task T014: "DaFontHunter in src/hunters/sources/dafont.py"
Task T016: "FontSpaceHunter in src/hunters/sources/fontspace.py"
Task T018: "BeFontsHunter in src/hunters/sources/befonts.py"
Task T020: "ArabicFontsHunter in src/hunters/sources/arabic_fonts.py"
```

---

## Implementation Strategy

### MVP First (Layers 1–3 + Google Fonts)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T005)
3. Complete T006 (SiblingFontHunter) + T008 (MkvExtractHunter)
4. Complete T010 (GoogleFontsHunter) — covers majority of free fonts
5. Complete T025 (bootstrap registration) with available hunters
6. **STOP and VALIDATE**: Run pipeline, check `mkvinfo` for font attachments
7. If working → continue with remaining Layer 4 hunters and SearchEngine

### Full Delivery

1. Setup → Foundational → All 9 hunters in parallel → Integration → FuzzyMatch cleanup → Polish
2. Each hunter independently testable via unit tests
3. Final validation: `pytest tests/unit/ -v` + manual pipeline run

### For Gemini `/speckit-implement`

Execute tasks sequentially by ID (T001 → T034). When a task is marked `[P]`, you may batch it with its test task. Each task specifies exact files and dependencies. Read `plan.md` for detailed design of each component.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to spec user stories for traceability
- All network hunters share `_hunter_utils.py` — changes there affect all
- Library scanner fuzzy pairing (SequenceMatcher for episode-subtitle matching) is UNRELATED to font fuzzy matching — do NOT touch
- `time.sleep()` is FORBIDDEN in async code — use `asyncio.sleep()` only
- Every `httpx.AsyncClient` must accept `proxy` parameter from config
- Every downloaded font must be verified with fontTools before caching
