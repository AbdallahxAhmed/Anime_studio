# Pipeline Control & Safety — Architecture & Safety Checklist

**Purpose**: Validate requirement quality for pipeline stop, checkpoint, undo, and test fix features
**Created**: 2026-06-07
**Depth**: Standard
**Audience**: Reviewer (PR)
**Focus Areas**: Data Safety, Hexagonal Boundaries, Async Control Flow

## Requirement Completeness

- [ ] CHK001 - Are checkpoint file format fields exhaustively defined with data types? [Completeness, Spec §FR-003]
- [ ] CHK002 - Are all three Resume dialog button behaviors specified (Resume/Start Fresh/Cancel)? [Completeness, Spec §FR-004,005,006]
- [ ] CHK003 - Is the run manifest auto-prune behavior specified when exactly at the limit (e.g., 10 manifests exist, new one written)? [Completeness, Spec §FR-017]
- [ ] CHK004 - Are requirements defined for what happens when `stop_event` is set during the font ingestion pre-step vs. during episode processing? [Completeness, Gap]
- [ ] CHK005 - Are requirements defined for partial undo (e.g., undo succeeds for 3 of 5 episodes, fails for 2)? [Completeness, Gap]
- [ ] CHK006 - Are undo requirements for the ASS subtitle file restoration specified separately from MKV restoration? [Completeness, Spec §FR-013]

## Requirement Clarity

- [ ] CHK007 - Is "finishes the current episode" quantified — does it mean after mux, after trash, or after report write? [Clarity, Spec §FR-002]
- [ ] CHK008 - Is "same library path" for checkpoint matching defined precisely (resolved path vs. user-entered string)? [Clarity, Spec §FR-004]
- [ ] CHK009 - Is "skip already-completed episodes" defined — by path match, by file existence check, or by checkpoint list only? [Clarity, Spec §FR-005]
- [ ] CHK010 - Is "restore original files" defined — does it mean move from trash (deleting trash copy) or copy from trash (keeping backup)? [Clarity, Spec §FR-013]

## Requirement Consistency

- [ ] CHK011 - Do checkpoint path requirements align with run manifest path requirements (both under `.anime_studio/`)? [Consistency, Spec §FR-003,010]
- [ ] CHK012 - Are undo manifest fields consistent with existing `TrashReceipt` model fields (`original_path`, `trash_path`)? [Consistency, Spec §FR-011]
- [ ] CHK013 - Does the "Stop button visible only during pipeline execution" requirement align with the existing "closeEvent confirmation" behavior? [Consistency, Spec §FR-007]
- [ ] CHK014 - Are the 4 test fix requirements consistent with the actual current test implementations? [Consistency, Spec §FR-020-023]

## Acceptance Criteria Quality

- [ ] CHK015 - Can SC-001 ("within 5 seconds") be objectively measured in automated tests? [Acceptance Criteria, Spec §SC-001]
- [ ] CHK016 - Can SC-004 ("byte-identical to trash copy") be verified without a real filesystem? [Acceptance Criteria, Spec §SC-004]
- [ ] CHK017 - Is SC-008 ("ready for mypy --strict") measurable given mypy has never been run on the project? [Acceptance Criteria, Spec §SC-008]

## Scenario Coverage

- [ ] CHK018 - Are requirements defined for concurrent stop + undo attempts? [Coverage, Exception Flow]
- [ ] CHK019 - Are requirements defined for checkpoint file written but pipeline crashes before completion? [Coverage, Exception Flow]
- [ ] CHK020 - Are requirements defined for undo when the library directory itself has been moved/renamed? [Coverage, Edge Case]
- [ ] CHK021 - Are recovery requirements defined for TOML write failures (disk full, permissions)? [Coverage, Exception Flow]

## Non-Functional Requirements

- [ ] CHK022 - Are performance requirements specified for undo operations on large runs (100+ episodes)? [Gap]
- [ ] CHK023 - Are checkpoint file size limits or episode count limits defined? [Gap]

## Dependencies & Assumptions

- [ ] CHK024 - Is the `tomli_w` dependency explicitly listed as required or is manual TOML serialization mandated? [Assumption]
- [ ] CHK025 - Is the assumption "run manifests are local to library directory" validated against the existing `.anime_studio/` location pattern? [Assumption]

## Hexagonal Boundary Compliance

- [ ] CHK026 - Are boundary rules for all new files documented (which layer imports which)? [Completeness, Spec §FR-022]
- [ ] CHK027 - Is it specified that UndoDialog MUST NOT import from `src.core` directly (only via signals/bootstrap)? [Clarity, Gap]
- [ ] CHK028 - Are AST boundary test update requirements defined to cover new files? [Completeness, Spec §FR-022]
