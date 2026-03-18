# Tasks: Update Startup Logic

**Input**: Design documents from `/specs/002-fix-startup-logic/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and session utility helpers.

- [x] T001 Create session utility in `src/utils/session.py` with hybrid ID generation logic
- [x] T002 Add `RunSession` (session_id, timestamps, status, args, error_info), `TenderArchive`, and `CustomerArchive` table definitions to `SCHEMA_SQL` in `src/db/schema.py` to match data-model.md
- [x] T002.1 [P] Create regression test in `tests/test_isolation.py` to verify data is archived before new run starts
- [x] T002.2 [P] Create integration test in `tests/test_persistence.py` to verify DB commits after each stage

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Update the data layer to support session isolation and archival.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Implement `archive_old_data` function in `src/db/repository.py` to move rows to shadow tables
- [x] T004 Add `RunSession` CRUD operations (create, update status) in `src/db/repository.py`
- [x] T005 Update all existing repository functions (`upsert_tender`, `upsert_customer`, etc.) to accept and store `session_id`
- [x] T006 [P] Update `results` table schema and repository functions to filter by `session_id`

**Checkpoint**: Foundation ready - session-aware data layer is in place.

---

## Phase 3: User Story 1 - Idempotent Startup (Priority: P1) 🎯 MVP

**Goal**: Run multiple times without mixing data by using sessions and pre-run archival.

**Independent Test**: Run `uv run rostender search-active` twice and verify `tenders` table only contains the second run's data, while `tenders_archive` contains the first run's data.

### Implementation for User Story 1

- [x] T007 Update `src/main.py` to generate a `session_id` at startup and inject it into `PipelineParams`
- [x] T008 [P] Update `src/stages/params.py` to include `session_id` field
- [x] T009 Implement archival trigger in `src/main.py` before starting any pipeline stage
- [x] T010 Update `run_search_active` in `src/stages/search_active.py` to pass `session_id` to repository calls
- [x] T011 Update `run_analyze_history` in `src/stages/analyze_history.py` to filter/save using `session_id`
- [x] T012 Update `run_extended_search` in `src/stages/extended_search.py` to use `session_id`
- [x] T013 Update `run_report` in `src/stages/report.py` to generate reports for the current `session_id` only

**Checkpoint**: User Story 1 complete - runs are isolated and idempotent.

---

## Phase 4: User Story 2 - Incremental Exports & Persistence (Priority: P2)

**Goal**: Save progress to DB and unique Excel files after every pipeline stage.

**Independent Test**: Run a stage, check `reports/` for a unique file like `report_[ID]_[Stage].xlsx`, and verify DB contains records even if the next stage fails.

### Implementation for User Story 2

- [x] T014 Update `src/reporter/excel_report.py` to accept an optional `stage` name and use unique filenames per `session_id`
- [x] T015 Implement atomic write logic (temp file -> rename) in `src/reporter/excel_report.py`
- [x] T016 [P] Add explicit `.commit()` calls and `run_report` triggers at the end of each stage's `run` function in `src/stages/`
- [x] T017 [P] Implement session status update (Success/Fail/Interrupted) in `src/main.py` using `try...finally`

---

## Phase 5: Polish & Cross-Cutting Concerns

- [x] T018 Update logging in `src/main.py` to include `session_id` in all log messages
- [x] T019 [P] Update `README.md` with information about run isolation and the new `RunSession` tracking
- [x] T020 [P] Add `clean-db` command to `src/main.py` for manual archival/cleanup
- [ ] T021 [US2] Implement session startup check in `src/main.py` to log warning if previous session was 'interrupted' or 'failed'

---

## Dependencies & Execution Order

- **Foundational (Phase 2)**: Depends on Phase 1 completion - BLOCKS US1.
- **User Story 1 (P1)**: Depends on Foundational Phase (Phase 2).
- **User Story 2 (P2)**: Depends on US1 completion (needs session-aware stages).
- **Polish (Final Phase)**: Depends on US2 completion.

---

## Parallel Opportunities

- T006 (Results repository) can run in parallel with T003-T005.
- T008 (Params update) can run in parallel with T007.
- T014-T015 (Excel report updates) can run in parallel with stage updates T010-T012.
- T016-T017 (Main loop hooks) can run in parallel with logging updates.

---

## Implementation Strategy

1. **MVP First**: Complete Phase 1, 2, and 3 to achieve basic run isolation.
2. **Persistence**: Add Phase 4 to ensure data is saved incrementally and exports are unique.
3. **Polish**: Final cleanup and documentation.
