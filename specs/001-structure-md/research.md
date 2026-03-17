# Research: Scraper Fallback Refactoring

## Decision: Registry Pattern for Fallbacks
**Rationale**: The Registry pattern provides a clean way to manage multiple procurement platform strategies. It allows for easy addition of new platforms without modifying the central dispatcher (`unified_fallback.py`), adhering to the Open-Closed Principle.
**Alternatives considered**: 
- Keep `if-elif` chain (Rejected: poor scalability).
- Dynamic module discovery via `pkgutil` (Rejected: overkill for 5-10 modules, manual registration is more explicit and easier to debug).

## Decision: Package Structure
**Rationale**: Moving fallbacks to `src/scraper/fallbacks/` cleans up the `src/scraper/` directory and makes the architecture more explicit.
**Alternatives considered**: Keep in `src/scraper/` (Rejected: directory clutter).

## Unknowns Resolved
- **Fallback Priority**: EIS > GPB > Rosatom > Roseltorg (confirmed from `unified_fallback.py`).
- **Registration Method**: Manual registration in `src/scraper/fallbacks/__init__.py` or via a `@register` decorator in `base.py`. I'll choose the decorator for better locality of code.

## Best Practices
- Use `abc.ABC` for the base fallback strategy to ensure consistency.
- Standardize the `extract_inn` signature: `async def extract_inn(page: Page, url: str) -> str | None`.
- Ensure each fallback handles its own logging for consistency.
