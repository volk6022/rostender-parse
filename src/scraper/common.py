"""Общие вспомогательные функции для скрейпинга rostender.info."""

from __future__ import annotations

import re

from loguru import logger
from playwright.async_api import Page
from src.config import EXCLUDE_KEYWORDS, SELECTORS
from src.scraper.browser import BASE_URL, polite_wait, safe_goto

# Короткий алиас для читаемости.
S = SELECTORS


async def _navigate_to_search(page: Page) -> None:
    """Перейти на главную → расширенный поиск (установить сессию + куки).

    Smart Navigation: Проверяет текущий URL перед переходом, чтобы избежать лишних загрузок.
    """
    search_url = f"{BASE_URL}/extsearch/advanced"

    # Если мы уже на странице поиска, пропускаем навигацию
    if page.url.rstrip("/") == search_url.rstrip("/"):
        logger.debug("Уже на странице расширенного поиска, пропускаем переход")
        return

    # Если мы на главной, переходим сразу в поиск. Если нет - сначала на главную (для кук).
    if BASE_URL not in page.url:
        await safe_goto(page, BASE_URL)
        await polite_wait()

    await safe_goto(page, search_url)
    await polite_wait()

    try:
        await page.wait_for_selector(
            "#states_chosen, #states + .chosen-container", timeout=10_000
        )
        logger.debug("Chosen-плагин инициализирован")
    except Exception:
        logger.debug("Chosen-контейнер не найден за 10 с, продолжаем...")


async def _fill_common_filters(
    page: Page,
    keywords: list[str],
    min_price: int,
    exclude_keywords: list[str] | None = None,
) -> None:
    """Заполнить общие фильтры формы расширенного поиска.

    Включает: ключевые слова, исключения, мин. цену, скрытие без цены.
    """
    # Ключевые слова: используем запятую как разделитель, согласно требованиям сайта.
    if keywords:
        val_kw = ", ".join(keywords)
        logger.info(f"Заполнение ключевых слов: {val_kw}")
        await page.focus(S["search_keywords_input"])
        await page.fill(S["search_keywords_input"], "")
        await page.type(S["search_keywords_input"], val_kw, delay=10)

        # Принудительно вызываем события, чтобы JS сайта "увидел" текст
        await page.evaluate(
            "sel => { const el = document.querySelector(sel); if (el) { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); } }",
            S["search_keywords_input"],
        )
        await page.keyboard.press("Tab")  # Уводим фокус для фиксации значения
        await page.wait_for_timeout(300)

    # Исключения (если переданы или из конфига)
    effective_exclude = (
        exclude_keywords if exclude_keywords is not None else EXCLUDE_KEYWORDS
    )
    if effective_exclude:
        val = ", ".join(effective_exclude)
        logger.info(f"Заполнение исключений: {val}")
        await page.focus(S["search_exceptions_input"])
        await page.fill(S["search_exceptions_input"], "")
        await page.type(S["search_exceptions_input"], val, delay=10)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(300)

    # Цена от: используем скрытое поле напрямую через JS,
    # т.к. disp-поле имеет maskMoney-плагин, который может мешать вводу.
    await page.evaluate(
        """
        ([val, selPrice, selDisp]) => {
            const elPrice = document.querySelector(selPrice);
            const elDisp = document.querySelector(selDisp);
            if (!elPrice) return;
            elPrice.value = val;
            if (elDisp && typeof jQuery !== 'undefined' && jQuery(elDisp).maskMoney) {
                jQuery(elDisp).maskMoney('mask', parseFloat(val));
            } else if (elDisp) {
                elDisp.value = val;
            }
        }
    """,
        [str(min_price), S["search_min_price"], S["search_min_price_disp"]],
    )

    # Скрывать без цены (checkbox visually hidden, use JS)
    await page.evaluate(
        "sel => { const el = document.querySelector(sel); if (el && !el.checked) el.click(); }",
        S["search_hide_price"],
    )


async def submit_search(page: Page, log_context: str = "") -> None:
    """Надежное нажатие кнопки «Искать».

    Ищет элемент с текстом 'Искать' (кнопку, ссылку или инпут) и нажимает его.
    """
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
        # Даем JS сайта время на обработку введенных данных (фильтры, маски и т.д.)
        await page.wait_for_timeout(500)

        # Проверяем видимость и нажимаем принудительно
        await search_btn_locator.wait_for(state="visible", timeout=5000)
        await search_btn_locator.click(force=True)
        logger.debug("Клик по кнопке «Искать» (через текст) выполнен")
    except Exception:
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
