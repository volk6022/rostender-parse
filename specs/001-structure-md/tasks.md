# Tasks: Align and Optimize Scraper Fallback Architecture

**Input**: Design documents from `/specs/001-structure-md/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: Existing unit tests MUST be used for verification. Baseline tests must pass before implementation.

**Organization**: Tasks are grouped by user story (migration of specific fallbacks) to enable incremental refactoring and validation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Exact file paths are included in descriptions

## Phase 1: Setup (Refactor Baseline)

**Purpose**: Baseline verification and initial package structure

- [ ] T001 Capture baseline metrics by running `uv run .specify/extensions/workflows/refactor/measure-metrics.sh --before`
- [ ] T002 Verify 100% test pass rate for all fallback-related tests by running `uv run pytest tests/`
- [ ] T003 Create fallback package directory `src/scraper/fallbacks/`
- [ ] T004 Create `src/scraper/fallbacks/__init__.py` for package initialization

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure for the Registry pattern

- [ ] T005 [P] Implement `FallbackStrategy` base class in `src/scraper/fallbacks/base.py`
- [ ] T006 [P] Implement `@register_fallback` decorator in `src/scraper/fallbacks/base.py`
- [ ] T007 Implement `FallbackRegistry` in `src/scraper/fallbacks/__init__.py`

**Checkpoint**: Infrastructure ready - fallback migration can now begin

---

## Phase 3: User Story 1 - EIS Fallback Migration (Priority: P1) 🎯 MVP

**Goal**: Modularize and register the EIS fallback strategy

**Independent Test**: `uv run pytest tests/test_eis_fallback.py` passes using the new modularized strategy

### Implementation for User Story 1

- [ ] T008 [P] [US1] Create modularized EIS fallback in `src/scraper/fallbacks/eis.py` using `EISFallback` class
- [ ] T009 [US1] Register `EISFallback` using `@register_fallback("eis")`
- [ ] T010 [US1] Update `tests/test_eis_fallback.py` to import from `src.scraper.fallbacks.eis` if necessary
- [ ] T011 [US1] Verify EIS fallback tests pass independently

**Checkpoint**: EIS fallback is fully functional and modularized

---

## Phase 4: User Story 2 - GPB Fallback Migration (Priority: P2)

**Goal**: Modularize and register the GPB fallback strategy

**Independent Test**: `pytest tests/test_gpb_fallback.py` (if exists) or manual verification of GPB extraction

### Implementation for User Story 2

- [ ] T012 [P] [US2] Create modularized GPB fallback in `src/scraper/fallbacks/gpb.py`
- [ ] T013 [US2] Register `GPBFallback` using `@register_fallback("gpb")`
- [ ] T014 [US2] Verify GPB fallback functionality independently

**Checkpoint**: GPB fallback is fully functional and modularized

---

## Phase 5: User Story 3 - Other Fallbacks Migration (Priority: P3)

**Goal**: Modularize and register Rosatom and Roseltorg fallbacks

**Independent Test**: Manual verification of Rosatom and Roseltorg extraction using the new strategies

### Implementation for User Story 3

- [ ] T015 [P] [US3] Create modularized Rosatom fallback in `src/scraper/fallbacks/rosatom.py`
- [ ] T016 [P] [US3] Create modularized Roseltorg fallback in `src/scraper/fallbacks/roseltorg.py`
- [ ] T017 [US3] Register `RosatomFallback` and `RoseltorgFallback`
- [ ] T018 [US3] Verify remaining fallbacks functionality independently

---

## Phase 6: User Story 4 - Dispatcher Integration & Finalization (Priority: P4)

**Goal**: Update the unified dispatcher to use the registry and finalize architecture

**Independent Test**: `pytest` for all fallbacks passes using `unified_fallback_extract_inn`

### Implementation for User Story 4

- [ ] T019 [US4] Refactor `src/scraper/unified_fallback.py` to use `FallbackRegistry`
- [ ] T020 [US4] Remove old fallback files: `src/scraper/eis_fallback.py`, `src/scraper/gpb_fallback.py`, etc.
- [ ] T021 [US4] Update `STRUCTURE.md` to reflect the new `src/scraper/fallbacks/` architecture
- [ ] T022 [US4] Run full integration test of the pipeline to ensure no regressions in INN extraction

---

## Phase 7: Polish & Cleanup

**Purpose**: Final documentation and metrics

- [ ] T023 [P] Update docstrings and comments in `src/scraper/fallbacks/`
- [ ] T024 Capture after metrics by running `.specify/extensions/workflows/refactor/measure-metrics.sh --after`
- [ ] T025 Verify quickstart.md instructions for adding a new fallback

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 - BLOCKS all migration stories
- **User Stories (Phase 3-5)**: Depend on Foundational (Phase 2)
- **Integration (Phase 6)**: Depends on all fallbacks being modularized (Phase 3-5)
- **Polish (Phase 7)**: Final step after all stories are complete

### Parallel Opportunities

- T005 and T006 can run in parallel
- Once Phase 2 is complete, US1, US2, and US3 implementation can run in parallel (T008, T012, T015, T016)

---

## Implementation Strategy

### MVP First (EIS Only)

1. Complete Phase 1 & 2
2. Complete Phase 3 (EIS Migration)
3. Temporarily update `unified_fallback.py` to test EIS through the registry
4. **STOP and VALIDATE**

### Incremental Delivery

1. Migrate GPB, Rosatom, Roseltorg one by one
2. Finalize dispatcher refactor
3. Cleanup and document
