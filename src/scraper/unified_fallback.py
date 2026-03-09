"""Единый интерфейс для всех внешних фоллбэков."""

from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

from src.scraper.source_links import parse_source_urls
from src.scraper.eis_fallback import extract_inn_from_eis
from src.scraper.gpb_fallback import extract_inn_from_gpb
from src.scraper.rosatom_fallback import extract_inn_from_rosatom
from src.scraper.roseltorg_fallback import extract_inn_from_roseltorg


async def unified_fallback_extract_inn(
    page: Page, source_urls_str: str | None
) -> str | None:
    """Пытается извлечь ИНН из доступных внешних источников.

    Args:
        page: Playwright-страница.
        source_urls_str: Строка с внешними ссылками (напр. "eis:url,gpb:url").

    Returns:
        ИНН или None.
    """
    if not source_urls_str:
        return None

    sources = parse_source_urls(source_urls_str)

    # Приоритет источников
    priority = ["eis", "gpb", "rosatom", "roseltorg"]

    for platform in priority:
        if platform in sources:
            url = sources[platform]
            logger.info(f"Пробуем фоллбэк {platform}: {url}")

            inn = None
            try:
                if platform == "eis":
                    inn = await extract_inn_from_eis(page, url)
                elif platform == "gpb":
                    inn = await extract_inn_from_gpb(page, url)
                elif platform == "rosatom":
                    inn = await extract_inn_from_rosatom(page, url)
                elif platform == "roseltorg":
                    inn = await extract_inn_from_roseltorg(page, url)
            except Exception as e:
                logger.error(f"Ошибка фоллбэка {platform}: {e}")

            if inn:
                logger.success(f"ИНН {inn} успешно извлечен через {platform}")
                return inn

    return None
