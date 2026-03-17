"""Package for procurement platform-specific fallback strategies."""

from src.scraper.fallbacks.base import FallbackStrategy, get_registry


class FallbackRegistry:
    """Central registry for fallback strategies."""

    @staticmethod
    def get_strategy(name: str) -> FallbackStrategy | None:
        """Get a specific strategy by name."""
        return get_registry().get(name)

    @staticmethod
    def get_all_strategies() -> dict[str, FallbackStrategy]:
        """Get all registered strategies."""
        return get_registry()
