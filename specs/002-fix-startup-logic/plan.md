# Implementation Plan: Update Startup Logic

**Branch**: `002-fix-startup-logic` | **Date**: 2026-03-17 | **Spec**: [specs/002-fix-startup-logic/spec.md](specs/002-fix-startup-logic/spec.md)
**Input**: Feature specification from `/specs/002-fix-startup-logic/spec.md`

## Summary
Implement a robust startup and run isolation mechanism using unique Session IDs. This includes data archival of previous results, transactional persistence at every stage, and incremental Excel reports with unique filenames to prevent data mixing and corruption.

## Technical Context

**Language/Version**: Python >=3.11  
**Primary Dependencies**: `uv`, `playwright`, `aiosqlite`, `loguru`, `pyyaml`, `openpyxl`  
**Storage**: SQLite (`aiosqlite`) with shadow archival tables  
**Testing**: `pytest` for regression and integration tests  
**Target Platform**: CLI/Local  
**Project Type**: CLI / Scraper-Parser Pipeline  
**Performance Goals**: <5s startup time; atomic database commits after each stage  
**Constraints**: Must preserve historical data while isolating active results  
**Scale/Scope**: ~100-1000 tenders per session; ~10 MB database growth per session  

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Modular Scraper-First: Does this feature use modular strategies for data sources?
- [x] Database-Centric: Does it communicate via SQLite repository?
- [x] Protocol-Driven: Is parsing decoupled from scraping?
- [x] Test-Driven: Are regression/unit tests planned?
- [x] Observability: Does it use loguru for structured logging?

## Project Structure

### Documentation (this feature)

```text
specs/002-fix-startup-logic/
├── plan.md              # This file
├── research.md          # Session ID and archival strategies
├── data-model.md        # New RunSession, TenderArchive, CustomerArchive tables
├── quickstart.md        # Verifying isolation and incremental saves
├── contracts/           
│   └── reports.md       # Incremental Excel naming convention
└── tasks.md             # To be generated via /speckit.tasks
```

### Source Code (repository root)

```text
src/
├── main.py              # Update startup/run loop with Session ID injection
├── db/
│   ├── schema.py        # Add sessions and archive tables
│   └── repository.py    # Update all CRUD to support session-based isolation
├── stages/              # Add .run() commit hooks and reporter calls
└── reporter/
    └── excel_report.py  # Update to support unique filename generation
```

**Structure Decision**: Enhancing the existing single-project structure with clear session-aware persistence logic in the `db/` and `stages/` directories.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | No violations detected | N/A |
