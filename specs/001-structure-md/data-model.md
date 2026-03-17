# Data Model & Architecture: Scraper Fallbacks

## Architecture Overview

The fallback system is based on the Strategy pattern. Each procurement platform (EIS, GPB, etc.) implements a common interface for INN extraction.

### Classes

#### `FallbackStrategy` (Abstract Base Class)
- **Purpose**: Defines the interface for all fallback strategies.
- **Methods**:
    - `extract_inn(page: Page, url: str) -> str | None` (Abstract): Implementation-specific logic to navigate and parse INN.

#### `FallbackRegistry`
- **Purpose**: Centralized management of strategies and their priorities.
- **Attributes**:
    - `_strategies`: Dict mapping platform keys (e.g., "eis") to strategy instances.
- **Methods**:
    - `register(key: str, strategy: FallbackStrategy)`: Add a strategy.
    - `get_strategy(key: str) -> FallbackStrategy | None`: Retrieve a strategy.
    - `get_all_strategies() -> dict[str, FallbackStrategy]`: List all registered platforms.

## Priority Order
The system will attempt fallbacks in the following order:
1. `eis`
2. `gpb`
3. `rosatom`
4. `roseltorg`
