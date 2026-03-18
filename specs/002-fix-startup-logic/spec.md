# Feature Specification: Update Startup Logic

**Feature Branch**: `002-fix-startup-logic`  
**Created**: 2026-03-17  
**Status**: Draft  
**Input**: User description: "i need to update startup logic, it need to make it able to run multiple times (now it mix old run data with new)"

## Clarifications
### Session 2026-03-17
- Q: How should incremental Excel reports be named? → A: Use unique names (e.g., `report_[SessionID]_[Stage].xlsx`)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Idempotent Startup (Priority: P1)

As a user, I want to run the parser multiple times without the results of previous runs contaminating or being mixed with the results of the current run.

**Why this priority**: This is critical for data integrity. Currently, the system mixes old and new data, making reports unreliable.

**Independent Test**: Can be tested by running the parser once, noting the results, running it again with different parameters or data, and verifying that the second run's output contains only the data expected for that run.

**Acceptance Scenarios**:

1. **Given** a database with data from a previous run, **When** the parser starts a new full run, **Then** the system MUST ensure that "active" or "pending" states from the previous run do not interfere with the current scraping session.
2. **Given** multiple consecutive runs, **When** examining the final report, **Then** the report MUST accurately reflect the specific run's scope without duplicating or merging unrelated historical records incorrectly.

---

### User Story 2 - Run Isolation & Incremental Exports (Priority: P2)

As a developer, I want a clear mechanism using unique session IDs that separates data by run and ensures all progress is saved to both the database and Excel files after every step.

**Why this priority**: Improves maintainability, allows for granular data management, prevents data loss if the pipeline is interrupted, and provides immediate visibility into the progress of each stage.

**Independent Test**: 
1. Verify that each run is associated with a unique session ID in the database.
2. Interrupt the process after a specific stage (e.g., Phase 1) and verify that all stage data is fully persisted in the database and an Excel file for that stage exists in the `reports/` directory.

**Acceptance Scenarios**:

1. **Given** the start of a new pipeline, **When** data is persisted, **Then** it MUST be associated with a unique session ID per run.
2. **Given** any completed pipeline stage, **When** the stage finishes, **Then** the system MUST commit all gathered data to the database AND generate an incremental Excel report containing the results of that stage before proceeding or exiting.
3. **Given** a stage completion, **When** the Excel report is generated, **Then** it MUST use a unique filename incorporating the Session ID and Stage name to prevent overwriting (e.g., `report_[SessionID]_[Stage].xlsx`).

---

### Edge Cases

- What happens when a run is interrupted? The session ID should allow identifying the partial run, and the incremental Excel files should remain accessible.
- How does the system handle "historical" data? Existing data should be archived to prevent "mixing" but allow later retrieval.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST generate and use a unique Session ID for every execution of the parser.
- **FR-002**: System MUST archive existing data in active tables (e.g., `tenders`, `customers`) before starting a new run to ensure isolation.
- **FR-003**: System MUST perform a database commit/save operation at the end of every pipeline stage.
- **FR-004**: System MUST trigger Excel report generation at the end of every pipeline stage (e.g., Phase 1 Search, Phase 2 Analysis).
- **FR-005**: All data persistence MUST use the `db/repository.py` layer, which must be updated to support session-based isolation.
- **FR-006**: All document extraction MUST be handled by dedicated `parser/` modules.
- **FR-007**: System MUST record the status (Success/Fail/Interrupted) of each session in a new `RunSession` table.
- **FR-008**: Incremental Excel files MUST be named uniquely using the format `report_[SessionID]_[Stage].xlsx`.

### Key Entities *(include if feature involves data)*

- **RunSession**: Represents a single execution of the parser. Attributes: `session_id` (UUID/Hash), `start_time`, `end_time`, `parameters`, `status`.
- **ArchiveTable**: Shadow tables for `tenders` and `customers` that store results from previous sessions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of "active tender" reports generated after a run contain only data discovered or updated during that specific run.
- **SC-002**: Data from interrupted runs is 100% recoverable up to the last completed stage via both database records and incremental Excel files.
- **SC-003**: No manual database intervention is required between consecutive `uv run rostender` commands to get clean results.
- **SC-004**: Users can verify the source run of any record in the database via a unique `session_id`.

## Assumptions

- We assume that "saving all data after every step" includes triggering the existing `reporter/` modules for intermediate Excel output.
- We assume that "archiving" means moving rows or tagging them such that standard "active" queries ignore previous session results.
