# Quickstart: Run Isolation Verification

## Environment Setup
1. Ensure `config.yaml` is configured with valid `rostender.info` credentials.
2. Initialize clean state (optional): 
   ```bash
   uv run rostender clean-db # (New command planned)
   ```

## Scenario 1: Multi-Run Data Isolation
1. Run the search stage:
   ```bash
   uv run rostender search-active --days-back 1
   ```
   - **Expected**: A new `RunSession` is created with `status='running'`.
   - **Expected**: Excel file `reports/report_[SessionID]_search-active.xlsx` is generated.
   
2. Run a second search stage with different parameters:
   ```bash
   uv run rostender search-active --days-back 14
   ```
   - **Expected**: Previous run results are moved to `TenderArchive` and `CustomerArchive`.
   - **Expected**: Active `Tender` table contains only results from the *new* session.
   - **Expected**: A new Excel file `reports/report_[SessionID2]_search-active.xlsx` exists.

## Scenario 2: Incremental Persistence (Interruption)
1. Start the analysis stage and interrupt with `Ctrl+C`:
   ```bash
   uv run rostender analyze-history
   # (Interrupt after a few tenders are processed)
   ```
   - **Expected**: `RunSession.status` is set to `interrupted`.
   - **Expected**: All tenders processed *before* the interruption are fully saved in the database with the current `session_id`.

## Scenario 3: Stage-Based Reporting
1. Run the full pipeline:
   ```bash
   uv run rostender
   ```
   - **Expected**: Multiple Excel files in `reports/` (one per stage).
   - **Expected**: `sessions` table shows a single `session_id` with `status='success'`.
   - **Expected**: `last_updated` timestamps on all records match the session start time window.

## Verification Queries (SQLite)
- Check current session: `SELECT * FROM sessions ORDER BY start_time DESC LIMIT 1;`
- Verify tender isolation: `SELECT COUNT(*), session_id FROM tenders GROUP BY session_id;` (Should only show 1 ID if not archived).
- Verify archival: `SELECT COUNT(*) FROM tenders_archive;` (Should show results from previous runs).
