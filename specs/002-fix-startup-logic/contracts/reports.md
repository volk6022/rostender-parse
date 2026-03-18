# Reports Contract: Incremental Excel Outputs

## Stage-Based File Naming
Incremental reports MUST use the following naming convention to ensure uniqueness and auditability:

```text
reports/report_[SessionID]_[Stage].xlsx
```

### Placeholders
- `[SessionID]`: Hybrid ID format (e.g., `20260317-143005-a1b2c3`).
- `[Stage]`: Lowercase stage identifier:
    - `search-active`: Phase 1 Search results.
    - `analyze-history`: Phase 2 Analysis metrics.
    - `extended-search`: Phase 3 Related findings.
    - `final`: Consolidated results from Phase 4.

## Expected Content by Stage
Each incremental report MUST include the following minimum data points:

### Stage 1: search-active
- **Tenders**: URL, Title, Price, Customer INN.
- **Status**: Discovered in this session.

### Stage 2: analyze-history
- **Tenders**: Historical analysis metrics (avg participants, competition ratio).
- **Protocol Data**: Extracted participant counts from DOCX/PDF/HTML.

### Stage 3: extended-search
- **Tenders**: Additional findings for customers flagged in Stage 2.

## Atomic Write Requirement
To prevent file corruption during interruption:
1. Write temporary file: `report_[SessionID]_[Stage].tmp.xlsx`.
2. Move/Rename to final filename: `report_[SessionID]_[Stage].xlsx`.
3. Verify file existence before signaling stage completion.
