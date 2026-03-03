"""Общие вспомогательные функции для скрейпинга rostender.info."""

from __future__ import annotations

import re

from loguru import logger
from playwright.async_api import Page
from src.config import SELECTORS
from src.scraper.browser import polite_wait


SEARCH_TEXT = re.compile(r"^Искать$", re.IGNORECASE)


async def submit_search(page: Page, log_context: str = "") -> None:
    """Надежное нажатие кнопки «Искать».

    Ищет элемент с текстом 'Искать' (кнопку, ссылку или инпут) и нажимает его.
    """
    S = SELECTORS
    context_str = f" {log_context}" if log_context else ""
    logger.debug(f"Нажимаем кнопку поиска{context_str}...")
    await page.keyboard.press("Escape")

    # Ищем кнопку по тексту "Искать", так как ID может быть нестабилен
    search_btn_locator = (
        page.locator("button, input[type='button'], input[type='submit'], .btn")
        .filter(has_text=re.compile(r"^Искать$", re.IGNORECASE))
        .first
    )

    try:
        # Проверяем видимость и нажимаем принудительно
        await search_btn_locator.wait_for(state="visible", timeout=5000)
        await search_btn_locator.click(force=True)
        logger.debug("Клик по кнопке «Искать» (через текст) выполнен")
    except Exception as e:
        # logger.warning(
        #     "Не удалось нажать кнопку по тексту ({}), пробуем через ID...", e
        # )
        try:
            await page.click(S["search_button"], force=True, timeout=5000)
            logger.debug("Клик по кнопке «Искать» (через ID) выполнен")
        except Exception as e2:
            logger.error("Все попытки нажать «Искать» провалились: {}", e2)
            # В крайнем случае пробуем нажать Enter в поле ключевых слов
            await page.focus(S["search_keywords_input"])
            await page.keyboard.press("Enter")
            logger.debug("Отправка формы через Enter в поле ключевых слов")

    await page.wait_for_load_state("load")
    await polite_wait()

    # # Пытаемся найти кнопку по тексту "Искать" (регистронезависимо)
    # # Используем фильтр по тексту, так как это наиболее стабильный способ
    # btn = page.locator("button, input[type='button'], input[type='submit'], .btn").filter(has_text=SEARCH_TEXT).first

    # try:
    #     # Ждем появления в DOM (даже если Playwright считает элемент скрытым/перекрытым)
    #     await btn.wait_for(state="attached", timeout=5000)
    #     # force=True позволяет кликнуть по координатам, даже если сверху другой элемент
    #     await btn.click(force=True)
    #     logger.debug(f"Клик по кнопке «Искать»{context_str} выполнен")
    # except Exception as e:
    #     logger.warning(
    #         f"Не удалось нажать кнопку по тексту ({e}), пробуем через селектор ID..."
    #     )
    #     try:
    #         await page.click(S["search_button"], force=True, timeout=5000)
    #         logger.debug(f"Клик по кнопке «Искать» через ID{context_str} выполнен")
    #     except Exception as e2:
    #         logger.error(f"Все попытки нажатия кнопки провалились{context_str}: {e2}")
    #         # В качестве последнего средства — Enter в текущем поле
    #         await page.keyboard.press("Enter")

    # Ждем загрузки результатов
    await page.wait_for_load_state("load")
    await polite_wait()
