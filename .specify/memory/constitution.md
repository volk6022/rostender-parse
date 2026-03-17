# [PROJECT_NAME] Constitution
<!-- Example: Spec Constitution, TaskFlow Constitution, etc. -->

## Core Principles

### [PRINCIPLE_1_NAME]
<!-- Example: I. Library-First -->
[PRINCIPLE_1_DESCRIPTION]
<!-- Example: Every feature starts as a standalone library; Libraries must be self-contained, independently testable, documented; Clear purpose required - no organizational-only libraries -->

### [PRINCIPLE_2_NAME]
<!-- Example: II. CLI Interface -->
[PRINCIPLE_2_DESCRIPTION]
<!-- Example: Every library exposes functionality via CLI; Text in/out protocol: stdin/args → stdout, errors → stderr; Support JSON + human-readable formats -->

### [PRINCIPLE_3_NAME]
<!-- Example: III. Test-First (NON-NEGOTIABLE) -->
[PRINCIPLE_3_DESCRIPTION]
<!-- Example: TDD mandatory: Tests written → User approved → Tests fail → Then implement; Red-Green-Refactor cycle strictly enforced -->

### [PRINCIPLE_4_NAME]
<!-- Example: IV. Integration Testing -->
[PRINCIPLE_4_DESCRIPTION]
<!-- Example: Focus areas requiring integration tests: New library contract tests, Contract changes, Inter-service communication, Shared schemas -->

### [PRINCIPLE_5_NAME]
<!-- Example: V. Observability, VI. Versioning & Breaking Changes, VII. Simplicity -->
[PRINCIPLE_5_DESCRIPTION]
<!-- Example: Text I/O ensures debuggability; Structured logging required; Or: MAJOR.MINOR.BUILD format; Or: Start simple, YAGNI principles -->

### VI. Workflow Selection
Development activities SHALL use the appropriate workflow type based on the nature of the work. Each workflow enforces specific quality gates and documentation requirements tailored to its purpose:

- **Feature Development** (`/specify`): New functionality - requires full specification, planning, and TDD approach
- **Bug Fixes** (`/bugfix`): Defect remediation - requires regression test BEFORE applying fix
- **Modifications** (`/modify`): Changes to existing features - requires impact analysis and backward compatibility assessment
- **Refactoring** (`/refactor`): Code quality improvements - requires baseline metrics, behavior preservation guarantee, and incremental validation
- **Hotfixes** (`/hotfix`): Emergency production issues - expedited process with deferred testing and mandatory post-mortem
- **Deprecation** (`/deprecate`): Feature sunset - requires phased rollout (warnings → disabled → removed), migration guide, and stakeholder approvals

The wrong workflow SHALL NOT be used - features must not bypass specification, bugs must not skip regression tests, and refactorings must not alter behavior.

## [SECTION_2_NAME]
<!-- Example: Additional Constraints, Security Requirements, Performance Standards, etc. -->

[SECTION_2_CONTENT]
<!-- Example: Technology stack requirements, compliance standards, deployment policies, etc. -->

## [SECTION_3_NAME]
<!-- Example: Development Workflow, Review Process, Quality Gates, etc. -->

[SECTION_3_CONTENT]
<!-- Example: Code review requirements, testing gates, deployment approval process, etc. -->

### Extension Workflows
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
<!-- Example: Constitution supersedes all other practices; Amendments require documentation, approval, migration plan -->

[GOVERNANCE_RULES]
<!-- Example: All PRs/reviews must verify compliance; Complexity must be justified; Use [GUIDANCE_FILE] for runtime development guidance -->

**Version**: [CONSTITUTION_VERSION] | **Ratified**: [RATIFICATION_DATE] | **Last Amended**: [LAST_AMENDED_DATE]
<!-- Example: Version: 2.1.1 | Ratified: 2025-06-13 | Last Amended: 2025-07-16 -->
