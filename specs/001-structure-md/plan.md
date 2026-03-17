# Implementation Plan: Align and Optimize Scraper Fallback Architecture

**Branch**: `001-structure-md` | **Date**: Tue Mar 17 2026 | **Spec**: `/specs/001-structure-md/spec.md`
**Input**: Feature specification from `/specs/001-structure-md/spec.md`

## Summary

Refactor the scraper's fallback architecture to improve maintainability and align with `STRUCTURE.md`. The current `if-elif` chain in `unified_fallback.py` will be replaced with a `FallbackRegistry` pattern. Fallback modules will be moved to a dedicated `src/scraper/fallbacks/` package, and `STRUCTURE.md` will be updated to include all supported platforms.

## Technical Context

**Language/Version**: Python >=3.11
**Primary Dependencies**: `playwright`, `aiosqlite`, `loguru`, `pyyaml`
**Storage**: SQLite (`data/rostender.db`)
**Testing**: `pytest` + `pytest-asyncio`
**Target Platform**: Windows (CLI tool)
**Project Type**: CLI
**Performance Goals**: Maintain extraction speed; ensure zero regressions in INN extraction accuracy.
**Constraints**: 2s polite delay between requests; depends on external procurement portal availability.
**Scale/Scope**: Unified handling of ~5 existing fallbacks (EIS, GPB, Rosatom, Roseltorg, GPB) with extensibility for more.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] Baseline metrics MUST be captured before any changes (Refactor Workflow)
- [x] Tests MUST pass after EVERY incremental change (Refactor Workflow)
- [x] Behavior preservation MUST be guaranteed (Refactor Workflow)
- [x] TDD approach for any new helper functions (Core Principles)

## Project Structure

### Documentation (this feature)

```text
specs/001-structure-md/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (CLI/Internal)
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/
├── scraper/
│   ├── fallbacks/       # New package
│   │   ├── __init__.py  # Registry logic
│   │   ├── base.py      # Base strategy class
│   │   ├── eis.py       # Moved from scraper/eis_fallback.py
│   │   ├── gpb.py       # Moved from scraper/gpb_fallback.py
│   │   └── ...
│   ├── unified_fallback.py # Updated to use registry
│   └── ...
```

**Structure Decision**: Option 1 (Single project) with a new sub-package `src/scraper/fallbacks/` to encapsulate platform-specific logic.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Strategy/Registry Pattern | Scalability & OCP compliance | Current if-elif chain is difficult to maintain and violates Open-Closed Principle. |

---
*Created by opencode*
