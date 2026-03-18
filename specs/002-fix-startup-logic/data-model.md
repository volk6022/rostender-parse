# Data Model: Run Isolation

## Entities

### RunSession
Represents a single execution of the parser pipeline.
- `session_id` (TEXT, PK): Unique identifier (e.g., `20260317-143005-a1b2c3`).
- `start_time` (DATETIME): UTC timestamp of run initiation.
- `end_time` (DATETIME, NULL): UTC timestamp of run completion.
- `status` (TEXT): One of `running`, `success`, `failed`, `interrupted`.
- `command_args` (TEXT, NULL): Full CLI command string for reproduction.
- `error_info` (TEXT, NULL): Captured exception or interruption details.

### Tender (Modified)
Updated to include a link to the session that discovered or updated it.
- `id` (INTEGER, PK): Primary key.
- `session_id` (TEXT, FK): References `RunSession.session_id`.
- `last_updated` (DATETIME): Timestamp of last modification in this session.
- (Existing fields like `tender_url`, `title`, `price`, `inn`, etc.)

### Customer (Modified)
Updated to include session tracking.
- `inn` (TEXT, PK): Customer INN.
- `session_id` (TEXT, FK): References `RunSession.session_id`.
- `last_updated` (DATETIME): Timestamp.
- (Existing fields)

### TenderArchive
Shadow table for storing tenders from previous sessions.
- Identical schema to `Tender` but with an additional `archived_at` timestamp.

### CustomerArchive
Shadow table for storing customers from previous sessions.
- Identical schema to `Customer` but with an additional `archived_at` timestamp.

## Relationships
- `RunSession` 1 -> N `Tender` (A session can discover multiple tenders).
- `RunSession` 1 -> N `Customer` (A session can discover multiple customers).
- `Tender` 1 -> 1 `RunSession` (A tender in the active table belongs to the current run).

## State Transitions
1. **Pipeline Start**: Create `RunSession` with `status='running'`.
2. **Archival Phase**: Move all rows from `Tender` and `Customer` to their respective archive tables.
3. **Stage Completion**: Update `RunSession` metadata (e.g., stage counters) and save.
4. **Pipeline Finish**: Set `status='success'` and record `end_time`.
5. **Exception/Interrupt**: Set `status='failed'` or `'interrupted'` in a `finally` block.
