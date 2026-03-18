# Research: Startup Logic & Run Isolation

## Decision: Session ID Generation
- **Chosen**: Hybrid approach (Timestamp + Short UUID suffix).
- **Format**: `YYYYMMDD-HHMMSS-xxxxxx` (e.g., `20260317-143005-a1b2c3`).
- **Rationale**: Combines human readability (easy sorting/identification) with technical uniqueness.
- **Alternatives considered**: 
    - Pure UUID: Robust but hard to distinguish in reports without checking timestamps.
    - Pure Timestamp: Risk of collisions if multiple processes start simultaneously.

## Decision: Data Archival Pattern
- **Chosen**: Shadow Tables (`tenders_archive`, `customers_archive`).
- **Mechanism**: Move rows from active tables to archive tables at the start of a new run.
- **Rationale**: Keeps active tables (`tenders`, `customers`) small and performant for the current scraping session. Historically analyzed data is preserved for reference but doesn't "mix" with new findings.
- **Alternatives considered**:
    - Tagging (status column): Simpler to implement but degrades performance over time and complicates "active" queries (must always filter `WHERE is_archived = 0`).

## Decision: Incremental Excel Exports
- **Chosen**: Atomic overwriting with unique filenames per stage.
- **Pattern**: `report_[SessionID]_[Stage].xlsx`.
- **Rationale**: Since the user requested "saving after every step", creating unique files per stage (Search, History, etc.) provides a clear audit trail and prevents corruption of previous stage data if a later stage crashes.
- **Alternatives considered**:
    - Appending to a single file: `openpyxl` is not optimized for frequent appends and risks file corruption if interrupted during a save.

## Decision: Session Tracking
- **Chosen**: Dedicated `RunSession` table.
- **Fields**: `session_id`, `start_time`, `end_time`, `status`, `command_args`, `error_info`.
- **Rationale**: Provides a formal registry of all runs, allowing the system to identify interrupted sessions and track overall pipeline health.
