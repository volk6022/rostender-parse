<!--
Sync Impact Report:
- Version change: [CONSTITUTION_VERSION] → 1.0.0
- List of modified principles:
  - [PRINCIPLE_1_NAME] → I. Modular Scraper-First
  - [PRINCIPLE_2_NAME] → II. Database-Centric Pipeline
  - [PRINCIPLE_3_NAME] → III. Protocol-Driven Parsing
  - [PRINCIPLE_4_NAME] → IV. Test-Driven Remediation
  - [PRINCIPLE_5_NAME] → V. Observability & Logging
- Added sections: VI. Workflow Selection, Quality Gates by Workflow
- Removed sections: None
- Templates requiring updates:
  - .specify/templates/plan-template.md (✅ updated)
  - .specify/templates/spec-template.md (✅ updated)
  - .specify/templates/tasks-template.md (✅ updated)
  - .specify/templates/checklist-template.md (✅ updated)
- Follow-up TODOs: None
-->

# Rostender Parser Constitution

## Core Principles

### I. Modular Scraper-First
Every data source MUST be implemented as a modular scraper strategy (e.g., `scraper/fallbacks/`). Scrapers MUST be self-contained, using `browser.py` for shared Playwright logic, and independently testable against mock HTML/PDF responses.

### II. Database-Centric Pipeline
The pipeline stages MUST communicate exclusively via the SQLite database (`db/repository.py`). Each stage MUST be runnable independently, reading its required inputs from the DB and persisting its results for subsequent stages. Direct memory passing between stages is PROHIBITED.

### III. Protocol-Driven Parsing
Document parsing (PDF/DOCX/HTML) MUST be decoupled from scraper logic. Parsers MUST use defined regex patterns or structured extractors (`parser/`) to return normalized data structures. Handlers for new document formats MUST be added as separate parser modules.

### IV. Test-Driven Remediation
Bug fixes MUST start with a failing regression test in `tests/` that reproduces the reported issue using captured data or mock responses. New features SHOULD include unit tests for core logic and integration tests for end-to-end stage execution.

### V. Observability & Logging
All stages MUST use `loguru` for structured logging. Critical failures MUST be logged with enough context (URL, Tender ID, Customer INN) to allow reproduction. The `data/` directory MUST be used for persistent logs and database storage.

### VI. Workflow Selection
Development activities SHALL use the appropriate workflow type based on the nature of the work. Each workflow enforces specific quality gates and documentation requirements tailored to its purpose:

- **Feature Development** (`/specify`): New functionality - requires full specification, planning, and TDD approach
- **Bug Fixes** (`/bugfix`): Defect remediation - requires regression test BEFORE applying fix
- **Modifications** (`/modify`): Changes to existing features - requires impact analysis and backward compatibility assessment
- **Refactoring** (`/refactor`): Code quality improvements - requires baseline metrics, behavior preservation guarantee, and incremental validation
- **Hotfixes** (`/hotfix`): Emergency production issues - expedited process with deferred testing and mandatory post-mortem
- **Deprecation** (`/deprecate`): Feature sunset - requires phased rollout (warnings → disabled → removed), migration guide, and stakeholder approvals

The wrong workflow SHALL NOT be used - features must not bypass specification, bugs must not skip regression tests, and refactorings must not alter behavior.

## Implementation Standards

### Technology Stack
- **Runtime**: Python >=3.11 with `uv` for dependency management.
- **Automation**: Playwright (Chromium) for web scraping.
- **Persistence**: `aiosqlite` for asynchronous database access.
- **Reporting**: `openpyxl` for Excel generation.

### Security & Credentials
- Credentials MUST NOT be committed to version control.
- Use `config.yaml` (excluded via `.gitignore`) with `config.yaml.example` as a template.
- Secrets MUST be handled as sensitive configuration parameters.

## Extension Workflows

### Command Interface
- **Bugfix**: `/bugfix "<description>"` → bug-report.md + tasks.md with regression test requirement
- **Modification**: `/modify <feature_num> "<description>"` → modification.md + impact analysis + tasks.md
- **Refactor**: `/refactor "<description>"` → refactor.md + baseline metrics + incremental tasks.md
- **Hotfix**: `/hotfix "<incident>"` → hotfix.md + expedited tasks.md + post-mortem.md (within 48 hours)
- **Deprecation**: `/deprecate <feature_num> "<reason>"` → deprecation.md + dependency scan + phased tasks.md

### Quality Gates by Workflow

**Feature Development**:
- Specification MUST be complete before planning
- Plan MUST pass constitution checks before task generation
- Tests MUST be written before implementation (TDD)
- Code review MUST verify constitution compliance

**Bugfix**:
- Bug reproduction MUST be documented with exact steps
- Regression test MUST be written before fix is applied
- Root cause MUST be identified and documented
- Prevention strategy MUST be defined

**Modification**:
- Impact analysis MUST identify all affected files and contracts
- Original feature spec MUST be linked
- Backward compatibility MUST be assessed
- Migration path MUST be documented if breaking changes

**Refactor**:
- Baseline metrics MUST be captured before any changes
- Tests MUST pass after EVERY incremental change
- Behavior preservation MUST be guaranteed (tests unchanged)
- Target metrics MUST show measurable improvement

**Hotfix**:
- Severity MUST be assessed (P0/P1/P2)
- Rollback plan MUST be prepared before deployment
- Fix MUST be deployed and verified before writing tests (exception to TDD)
- Post-mortem MUST be completed within 48 hours of resolution

**Deprecation**:
- Dependency scan MUST be run to identify affected code
- Migration guide MUST be created before Phase 1
- All three phases MUST complete in sequence (no skipping)
- Stakeholder approvals MUST be obtained before starting

## Governance
This constitution supersedes all other documentation regarding project standards. Amendments require a version bump and an updated Sync Impact Report.

**Version**: 1.0.0 | **Ratified**: 2026-03-17 | **Last Amended**: 2026-03-17
