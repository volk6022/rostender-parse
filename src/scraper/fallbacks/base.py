"""Base strategy and registration for fallbacks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Type

if TYPE_CHECKING:
    from playwright.async_api import Page


class FallbackStrategy(ABC):
    """Base class for all fallback strategies."""

    @abstractmethod
    async def extract_inn(self, page: Page, url: str) -> str | None:
        """Extract INN from the given page and URL."""
        pass


_registry: dict[str, FallbackStrategy] = {}


def register_fallback(
    name: str,
) -> Callable[[Type[FallbackStrategy]], Type[FallbackStrategy]]:
    """Decorator to register a fallback strategy."""

    def decorator(cls: Type[FallbackStrategy]) -> Type[FallbackStrategy]:
        _registry[name] = cls()
        return cls

    return decorator


def get_registry() -> dict[str, FallbackStrategy]:
    """Get the registry of all fallback strategies."""
    return _registry
