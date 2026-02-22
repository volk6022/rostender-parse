"""Модуль для поиска завершённых (исторических) тендеров по ИНН заказчика."""

from __future__ import annotations

from typing import Any

from loguru import logger
from playwright.async_api import Page

from src.config import (
    HISTORICAL_TENDERS_LIMIT,
    MIN_PRICE_HISTORICAL,
    SEARCH_KEYWORDS,
    SELECTORS,
)
from src.scraper.active_tenders import parse_tenders_on_page
from src.scraper.browser import BASE_URL, polite_wait, safe_goto

# Короткий алиас для читаемости.
S = SELECTORS


async def search_historical_tenders(
    page: Page,
    customer_inn: str,
    *,
    limit: int = HISTORICAL_TENDERS_LIMIT,
) -> list[dict[str, Any]]:
    """Ищет завершённые тендеры заказчика на rostender.info.

    Фильтры (по плану, Этап 2.1):
      - Заказчик: ИНН
      - Ключевые слова: общие ``SEARCH_KEYWORDS``
      - Этап: «Завершён» (value="100")
      - Цена от: ``MIN_PRICE_HISTORICAL`` (1 000 000 ₽)
      - Скрывать тендеры без цены

    Исключения (``EXCLUDE_KEYWORDS``) **не** применяются: при поиске по
    конкретному ИНН заказчика мы хотим видеть все его поставочные тендеры
    без дополнительной фильтрации.

    Даты **не** ограничиваются — ищем по всей доступной истории.

    Args:
        page: Playwright-страница.
        customer_inn: ИНН заказчика.
        limit: Максимальное число тендеров для возврата
               (по умолчанию ``HISTORICAL_TENDERS_LIMIT``).

    Returns:
        Список словарей ``{tender_id, title, url, price, status}``,
        ограниченный *limit* записями.  ``status`` = ``"completed"``.
    """
    logger.info(
        "Поиск завершённых тендеров для ИНН {} (лимит: {})",
        customer_inn,
        limit,
    )

    # ── 1. Переход на страницу расширенного поиска ────────────────────────
    await safe_goto(page, f"{BASE_URL}/extsearch/advanced")

    # ── 2. Заполнение фильтров ───────────────────────────────────────────

    # Заказчик (ИНН)
    await page.fill(S["search_customers_input"], customer_inn)

    # Ключевые слова (общие, не из конкретного тендера)
    keywords_str = ", ".join(SEARCH_KEYWORDS)
    await page.fill(S["search_keywords_input"], keywords_str)

    # Цена от: MIN_PRICE_HISTORICAL через JS (maskMoney)
    await page.evaluate(
        """
        ([val, selPrice, selDisp]) => {
            document.querySelector(selPrice).value = val;
            const disp = document.querySelector(selDisp);
            if (disp && typeof jQuery !== 'undefined' && jQuery(disp).maskMoney) {
                jQuery(disp).maskMoney('mask', parseFloat(val));
            } else {
                disp.value = val;
            }
        }
    """,
        [str(MIN_PRICE_HISTORICAL), S["search_min_price"], S["search_min_price_disp"]],
    )

    # Скрывать без цены
    await page.check(S["search_hide_price"])

    # Этап: Завершён (value="100")
    await page.evaluate(
        """
        ([val, sel]) => {
            const select = document.querySelector(sel);
            Array.from(select.options).forEach(opt => opt.selected = (opt.value == val));
            $(select).trigger('chosen:updated');
        }
    """,
        ["100", S["search_states"]],
    )

    # Даты НЕ устанавливаем — ищем по всей истории.

    # ── 3. Нажимаем «Искать» ─────────────────────────────────────────────
    await page.click(S["search_button"])
    await page.wait_for_load_state("networkidle")

    # ── 4. Собираем результаты (пагинация, но не более limit) ─────────────
    all_tenders: list[dict[str, Any]] = []
    page_num = 1

    while len(all_tenders) < limit:
        logger.debug(
            "Исторический поиск (ИНН {}): страница #{}...",
            customer_inn,
            page_num,
        )

        # Проверяем наличие карточек
        rows = await page.query_selector_all(S["tender_card"])
        if not rows:
            if page_num == 1:
                logger.info("Завершённые тендеры не найдены для ИНН {}", customer_inn)
            break

        # Парсим текущую страницу (переиспользуем парсер из active_tenders)
        page_tenders = await parse_tenders_on_page(
            page,
            tender_status="completed",
        )
        all_tenders.extend(page_tenders)
        logger.debug(
            "Страница {}: найдено {} (всего: {})",
            page_num,
            len(page_tenders),
            len(all_tenders),
        )

        # Достигли лимита — не нужно листать дальше
        if len(all_tenders) >= limit:
            break

        # Проверяем наличие кнопки «Следующая»
        next_btn = await page.query_selector(S["pagination_next"])
        if not next_btn:
            logger.debug("Следующей страницы нет — пагинация завершена")
            break

        await next_btn.click()
        await page.wait_for_load_state("networkidle")
        await polite_wait()
        page_num += 1

    # Обрезаем до лимита (на случай, если на странице было больше)
    result = all_tenders[:limit]
    logger.info("Итого завершённых тендеров для ИНН {}: {}", customer_inn, len(result))
    return result
