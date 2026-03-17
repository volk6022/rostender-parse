"""Unified interface for all external fallbacks using the Registry pattern."""

from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

from src.scraper.source_links import parse_source_urls
from src.scraper.fallbacks import FallbackRegistry

# Import all strategies to ensure they are registered
import src.scraper.fallbacks.eis  # noqa: F401
import src.scraper.fallbacks.gpb  # noqa: F401
import src.scraper.fallbacks.rosatom  # noqa: F401
import src.scraper.fallbacks.roseltorg  # noqa: F401


async def unified_fallback_extract_inn(
    page: Page, source_urls_str: str | None
) -> str | None:
    """Attempts to extract INN from available external sources.

    Args:
        page: Playwright page.
        source_urls_str: String with external links (e.g. "eis:url,gpb:url").

    Returns:
        INN or None.
    """
    if not source_urls_str:
        return None

    sources = parse_source_urls(source_urls_str)

    # Priority of sources
    priority = ["eis", "gpb", "rosatom", "roseltorg"]

    for platform in priority:
        if platform in sources:
            url = sources[platform]
            strategy = FallbackRegistry.get_strategy(platform)

            if not strategy:
                logger.warning(f"No strategy registered for platform: {platform}")
                continue

            logger.info(f"Пробуем фоллбэк {platform}: {url}")

            try:
                inn = await strategy.extract_inn(page, url)
                if inn:
                    logger.success(f"ИНН {inn} успешно извлечен через {platform}")
                    return inn
            except Exception as e:
                logger.error(f"Ошибка фоллбэка {platform}: {e}")

    return None
