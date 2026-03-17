# Refactor Spec: Align and Optimize Scraper Fallback Architecture

**Refactor ID**: refactor-001
**Branch**: `refactor/001-structure-md`
**Created**: Tue Mar 17 2026
**Type**: [ ] Performance | [x] Maintainability | [ ] Security | [x] Architecture | [ ] Tech Debt
**Impact**: [ ] High Risk | [x] Medium Risk | [ ] Low Risk
**Status**: [x] Planning | [ ] Baseline Captured | [ ] In Progress | [ ] Validation | [ ] Complete

## Input
User description: "@STRUCTURE.md"

## Motivation

### Current State Problems
**Code Smell(s)**:
- [x] Tight Coupling (Unified fallback depends on all specific fallbacks)
- [x] God Object/Function (`unified_fallback_extract_inn` has growing if-elif chain)
- [x] Documentation Rot (`STRUCTURE.md` is missing several fallback modules)
- [x] Violation of Open-Closed Principle (Adding a new platform requires modifying `unified_fallback.py`)

**Concrete Examples**:
- `src/scraper/unified_fallback.py`: Lines 42-49 contain a hardcoded list of platforms and their corresponding functions.
- `src/scraper/`: Multiple files like `rosatom_fallback.py`, `gpb_fallback.py`, `roseltorg_fallback.py` are present but not reflected in the architecture overview.

### Business/Technical Justification
- **Developer velocity impact**: Adding support for new procurement platforms is cumbersome and requires modifying the dispatcher logic.
- **Maintainability**: The current structure makes it hard to track which platforms are supported and how they are prioritized.

## Proposed Improvement

### Refactoring Pattern/Technique
**Primary Technique**: Strategy Pattern with Registry

**High-Level Approach**:
1. Implement a `FallbackRegistry` that allows platforms to register their INN extraction strategies.
2. Move individual platform fallbacks into a `src/scraper/fallbacks/` sub-package.
3. Update `unified_fallback.py` to use the registry instead of hardcoded imports and logic.
4. Update `STRUCTURE.md` to reflect the new modular fallback architecture.

**Files Affected**:
- **Modified**: 
    - `src/scraper/unified_fallback.py`
    - `STRUCTURE.md`
- **Created**: 
    - `src/scraper/fallbacks/__init__.py`
    - `src/scraper/fallbacks/base.py`
    - `src/scraper/fallbacks/eis.py` (moved)
    - `src/scraper/fallbacks/gpb.py` (moved)
    - `src/scraper/fallbacks/rosatom.py` (moved)
    - `src/scraper/fallbacks/roseltorg.py` (moved)
- **Deleted**: 
    - `src/scraper/eis_fallback.py`
    - `src/scraper/gpb_fallback.py`
    - `src/scraper/rosatom_fallback.py`
    - `src/scraper/roseltorg_fallback.py`

### Design Improvements
**Before**:
```
unified_fallback.py → eis_fallback.py
                    → gpb_fallback.py
                    → rosatom_fallback.py
```

**After**:
```
unified_fallback.py → FallbackRegistry
                        ↑ (registers)
                      EISFallback, GPBFallback, ...
```

## Baseline Metrics
*Captured before refactoring begins - see metrics-before.md*

### Code Complexity
- **Cyclomatic Complexity**: [Not measured]
- **Cognitive Complexity**: [Not measured]
- **Lines of Code**: [To be calculated]

## Behavior Preservation Guarantee
*CRITICAL: Refactoring MUST NOT change external behavior*

### External Contracts Unchanged
- [x] `unified_fallback_extract_inn` signature remains the same.
- [x] Priority of platforms (EIS > GPB > Rosatom > Roseltorg) is preserved.
- [x] CLI arguments and config parameters are unchanged.

### Test Suite Validation
- [x] **All existing tests MUST pass WITHOUT modification**
- [x] Specifically `tests/test_eis_fallback.py` and any integration tests involving fallbacks.

### Behavioral Snapshot
**Key behaviors to preserve**:
1. Given a source URL string containing "eis:...", the system must correctly extract INN from EIS.
2. If multiple sources are present, they must be tried in the defined priority order.
3. Failures in one fallback must not stop the attempt of the next one in priority.

**Test**: Run existing `pytest` suite. Outputs and DB state must be consistent with baseline.

## Risk Assessment

### Risk Level Justification
**Why Medium Risk**:
Refactoring affects the core fallback logic used when rostender.info doesn't provide INN. If broken, it might reduce the system's ability to identify customers, leading to fewer "interesting" tenders found. However, it's covered by unit tests for individual fallbacks.

### Potential Issues
- **Risk 1**: Circular imports when setting up the registry.
  - **Mitigation**: Use a central registry module or lazy registration in `__init__.py`.

## Implementation Plan

### Phase 1: Baseline (Before Refactoring)
1. Capture all baseline metrics (run `.specify/extensions/workflows/refactor/measure-metrics.sh`).
2. Ensure 100% test pass rate.

### Phase 2: Refactoring (Incremental)
1. Create `src/scraper/fallbacks/` package and base classes.
2. Move one fallback at a time and register it.
3. Update `unified_fallback.py` to use the registry for that specific platform.
4. Verify tests pass at each step.

### Phase 3: Validation
1. Run full test suite.
2. Compare behavioral snapshot.

### Phase 4: Documentation
1. Update `STRUCTURE.md` to reflect the new structure.
