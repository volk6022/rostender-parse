"""Модуль для поиска завершённых (исторических) тендеров по ИНН заказчика."""

from __future__ import annotations

import re
from typing import Any
import asyncio

from loguru import logger
from playwright.async_api import Page

from src.config import SELECTORS
from src.scraper.active_tenders import parse_tenders_on_page
from src.scraper.common import (
    _navigate_to_search,
    _fill_common_filters,
    submit_search,
)
from src.scraper.browser import BASE_URL, polite_wait, safe_goto

# Короткий алиас для читаемости.
S = SELECTORS


# ── Внутренние хелперы (Historical Specific) ────────────────────────────────


async def _fill_historical_filters(
    page: Page,
    customer_inn: str,
    keywords: list[str],
    min_price: int,
) -> None:
    """Заполнить фильтры для поиска завершенных тендеров."""
    # 1. Заказчик (ИНН) - специфично для поиска по ИНН
    await page.fill(S["search_customers_input"], customer_inn)
    await page.wait_for_timeout(300)
    await page.keyboard.press("Escape")

    # 2. Общие фильтры (Ключевые слова, Цена, Скрывать без цены)
    # Исключения (EXCLUDE_KEYWORDS) не применяются для истории по ИНН
    await _fill_common_filters(page, keywords, min_price, exclude_keywords=[])

    # 3. Специфичный фильтр - Этап: Завершён (value="100")
    selected_value = await page.evaluate(
        """
        ([val, sel]) => {
            const select = document.querySelector(sel);
            if (!select) return null;
            Array.from(select.options).forEach(opt => opt.selected = (opt.value == val));
            if (typeof jQuery !== 'undefined' && jQuery(select).trigger) {
                jQuery(select).trigger('chosen:updated');
                jQuery(select).trigger('change');
            }
            return select.value;
        }
    """,
        ["100", S["search_states"]],
    )
    logger.debug("Фильтр «Этап» установлен: selected_value={}", selected_value)


def extract_keywords_from_title(title: str) -> list[str]:
    """Извлекает ключевые слова из заголовка тендера для поиска похожих тендеров.

    **Fix 3:** Полный заголовок **не** добавляется как ключевое слово — он может
    содержать 100-200 символов (номер тендера, год, название организации), что
    резко сужает результаты поиска (все слова должны совпадать).

    Вместо этого:
      1. Убираем ведущие номера/коды тендера (``"223785 Ремонт..."`` → ``"Ремонт..."``).
      2. Берём первую смысловую фразу (до запятой/скобки), ограничиваем ~60 символами.
      3. Добавляем значимые отдельные слова (>5 букв).
      4. Добавляем совпадения из ``SEARCH_KEYWORDS``.

    Например: ``"223785 Ремонт тепловой изоляции и обмуровки оборудования на 2026-2028"``
    → ``["Ремонт тепловой изоляции и обмуровки оборудования", "Ремонт", "Тепловой",
         "Изоляции", "Обмуровки", "Оборудование"]``

    Args:
        title: Заголовок тендера.

    Returns:
        Список ключевых слов для поиска (до 10 штук).
    """
    from src.config import SEARCH_KEYWORDS

    if not title or not title.strip():
        return []

    # ── Очистка заголовка ──────────────────────────────────────────────────
    # Убираем ведущие номера/коды тендера и лишние пробелы
    clean_title = re.sub(r"^\d[\d\s\-./]*", "", title).strip()
    if not clean_title:
        clean_title = title.strip()

    title_lower = clean_title.lower()

    keywords: list[str] = []

    # ── 1. Первая смысловая фраза (до запятой / скобки), макс. 60 символов ─
    if len(clean_title) > 5:
        first_part = clean_title.split(",")[0].split("(")[0].strip()
        # Убираем хвосты вида «на 2026-2028 гг.» / «для ООО «...»»
        first_part = re.sub(r"\s+(?:на|для|от|до|по|в)\s+\d.*$", "", first_part).strip()
        if len(first_part) > 60:
            # Обрезаем по границе слова
            first_part = " ".join(first_part[:60].split(" ")[:-1])
        if len(first_part) >= 3:
            keywords.append(first_part)

    # ── 2. Значимые отдельные слова (>= 4 буквы, не стоп-слова) ────────────
    words = re.findall(r"\b\w{4,}\b", title_lower)

    _stop_words = {
        "для",
        "что",
        "это",
        "котор",
        "таким",
        "товар",
        "работ",
        "услуг",
        "года",
        "годы",
        "период",
        "будет",
        "также",
        "более",
        "всего",
    }
    important_words = [w for w in words if w not in _stop_words]

    for word in important_words[:5]:
        if len(word) >= 4:
            keywords.append(word.capitalize())

    # ── 3. Совпадения с SEARCH_KEYWORDS ────────────────────────────────────
    for general_kw in SEARCH_KEYWORDS:
        if general_kw.lower() in title_lower:
            if general_kw not in keywords:
                keywords.append(general_kw)
            for gen_kw in SEARCH_KEYWORDS:
                if gen_kw not in keywords and (
                    gen_kw.lower() in title_lower
                    or any(word in gen_kw.lower() for word in important_words[:3])
                ):
                    keywords.append(gen_kw)

    # ── 4. Дедупликация ────────────────────────────────────────────────────
    seen: set[str] = set()
    unique_keywords: list[str] = []
    for kw in keywords:
        kw_normalized = kw.lower().strip()
        if kw_normalized not in seen and len(kw_normalized) > 2:
            seen.add(kw_normalized)
            unique_keywords.append(kw)

    return unique_keywords[:10]


async def search_historical_tenders(
    page: Page,
    customer_inn: str,
    *,
    limit: int = 5,
    custom_keywords: list[str] | None = None,
    min_price: int = 1_000_000,
) -> list[dict[str, Any]]:
    """Ищет завершённые тендеры заказчика на rostender.info.

    Фильтры (по плану, Этап 2.1):
      - Заказчик: ИНН
      - Ключевые слова: общие ``SEARCH_KEYWORDS`` ИЛИ ``custom_keywords``
      - Этап: «Завершён» (value="100")
      - Цена от: ``min_price``
      - Скрывать тендеры без цены

    Исключения (``EXCLUDE_KEYWORDS``) **не** применяются: при поиске по
    конкретному ИНН заказчика мы хотим видеть все его поставочные тендеры
    без дополнительной фильтрации.

    Даты **не** ограничиваются — ищем по всей доступной истории.

    Args:
        page: Playwright-страница.
        customer_inn: ИНН заказчика.
        limit: Максимальное число тендеров для возврата.
        custom_keywords: Кастомный список ключевых слов для поиска.
                         Если None — используются ``SEARCH_KEYWORDS``.
        min_price: Минимальная цена для поиска.

    Returns:
        Список словарей ``{tender_id, title, url, price, status}``,
        ограниченный *limit* записями.  ``status`` = ``"completed"``.
    """
    from src.config import (
        HISTORICAL_TENDERS_LIMIT,
        MIN_PRICE_HISTORICAL,
        SEARCH_KEYWORDS,
    )

    effective_limit = limit if limit is not None else HISTORICAL_TENDERS_LIMIT
    effective_min_price = min_price if min_price is not None else MIN_PRICE_HISTORICAL

    logger.info(
        "Поиск завершённых тендеров для ИНН {} (лимит: {}, ключевые слова: {})",
        customer_inn,
        effective_limit,
        "custom" if custom_keywords else "general",
    )

    # Используем кастомные ключевые слова или общие
    keywords = custom_keywords if custom_keywords else SEARCH_KEYWORDS

    # ── 1. Навигация и заполнение фильтров ────────────────────────────────
    await _navigate_to_search(page)
    await _fill_historical_filters(page, customer_inn, keywords, effective_min_price)

    # ── 2. Нажимаем «Искать» ─────────────────────────────────────────────
    await submit_search(page, f"ИНН {customer_inn}")

    # Логируем URL после поиска для диагностики применённых фильтров
    current_url = page.url

    logger.debug("URL после поиска: {}", current_url)

    # Ждём появления результатов (карточки тендеров) или пустого списка
    try:
        await page.wait_for_selector(
            f"{S['tender_card']}, .search-nothing, .search-results",
            timeout=30_000,
        )
    except Exception:
        logger.debug("Селектор результатов не найден, продолжаем...")

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
        await page.wait_for_load_state("load")
        try:
            await page.wait_for_selector(S["tender_card"], timeout=15_000)
        except Exception:
            logger.debug("Карточки тендеров не появились на странице {}", page_num + 1)
        await polite_wait()
        page_num += 1

    # Обрезаем до лимита (на случай, если на странице было больше)
    result = all_tenders[:limit]
    logger.info("Итого завершённых тендеров для ИНН {}: {}", customer_inn, len(result))
    return result
