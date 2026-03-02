"""Модуль для поиска активных тендеров на rostender.info."""

import re
from datetime import datetime
from typing import Any

from loguru import logger
from playwright.async_api import Page

from src.config import (
    EXCLUDE_KEYWORDS,
    MIN_PRICE_ACTIVE,
    MIN_PRICE_RELATED,
    SELECTORS,
)
from src.scraper.browser import BASE_URL, polite_wait, safe_goto

# Короткий алиас для читаемости.
S = SELECTORS


# ── Внутренние хелперы (DRY) ─────────────────────────────────────────────────


async def _navigate_to_search(page: Page) -> None:
    """Перейти на главную → расширенный поиск (установить сессию + куки)."""
    await safe_goto(page, BASE_URL)
    await polite_wait()
    await safe_goto(page, f"{BASE_URL}/extsearch/advanced")


async def _fill_common_filters(
    page: Page,
    keywords: list[str],
    min_price: int,
) -> None:
    """Заполнить общие фильтры формы расширенного поиска.

    Включает: ключевые слова, исключения, мин. цену, скрытие без цены,
    этап «Прием заявок», исключение аукционов и ед. поставщика.
    """
    # Ключевые слова
    await page.fill(S["search_keywords_input"], ", ".join(keywords))

    # Исключения
    await page.fill(S["search_exceptions_input"], ", ".join(EXCLUDE_KEYWORDS))

    # Цена от: используем скрытое поле напрямую через JS,
    # т.к. disp-поле имеет maskMoney-плагин, который может мешать вводу.
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
        [str(min_price), S["search_min_price"], S["search_min_price_disp"]],
    )

    # Скрывать без цены (checkbox visually hidden, use JS)
    await page.evaluate(
        "sel => { const el = document.querySelector(sel); if (el && !el.checked) el.click(); }",
        S["search_hide_price"],
    )

    # Этап: Прием заявок (значение "10").
    # Используем jQuery + Chosen plugin.
    await page.evaluate(
        """
        ([val, sel]) => {
            const select = document.querySelector(sel);
            Array.from(select.options).forEach(opt => opt.selected = (opt.value == val));
            $(select).trigger('chosen:updated');
        }
    """,
        ["10", S["search_states"]],
    )

    # Способ размещения: исключить Аукционы (1) и Ед. поставщик (28)
    await page.evaluate(
        """
        ([exclude_vals, sel]) => {
            const select = document.querySelector(sel);
            Array.from(select.options).forEach(opt => {
                if (exclude_vals.includes(opt.value)) {
                    opt.selected = false;
                } else {
                    opt.selected = true;
                }
            });
            $(select).trigger('chosen:updated');
        }
    """,
        [["1", "28"], S["search_placement_ways"]],
    )


async def _submit_and_collect(
    page: Page,
    *,
    log_context: str = "",
    empty_warning: str = "Результаты поиска не найдены",
) -> list[dict[str, Any]]:
    """Нажать «Искать» и собрать результаты со всех страниц пагинации.

    Args:
        page: Playwright-страница с заполненной формой.
        log_context: Контекст для лог-сообщений (напр. ``"для ИНН 123"``).
        empty_warning: Сообщение, если на первой странице нет результатов.
    """
    await page.click(S["search_button"])
    await page.wait_for_load_state("load")
    await polite_wait()

    all_tenders: list[dict[str, Any]] = []
    page_num = 1

    while True:
        logger.info("Парсинг страницы #{} {}...", page_num, log_context)

        rows = await page.query_selector_all(S["tender_card"])
        if not rows:
            if page_num == 1:
                logger.warning(empty_warning) if not log_context else logger.info(
                    empty_warning
                )
            break

        page_tenders = await parse_tenders_on_page(page)
        all_tenders.extend(page_tenders)
        logger.info(
            "Страница {}: найдено {} тендеров (всего: {})",
            page_num,
            len(page_tenders),
            len(all_tenders),
        )

        next_btn = await page.query_selector(S["pagination_next"])
        if not next_btn:
            logger.debug("Следующей страницы нет — пагинация завершена")
            break

        await next_btn.click()
        await page.wait_for_load_state("load")
        await polite_wait()
        page_num += 1

    return all_tenders


# ── Парсинг карточек ─────────────────────────────────────────────────────────


async def parse_tenders_on_page(
    page: Page,
    *,
    tender_status: str = "active",
) -> list[dict[str, Any]]:
    """
    Парсит карточки тендеров на текущей странице результатов.

    Args:
        page: Playwright-страница с результатами поиска.
        tender_status: Статус для записи в результат ("active" / "completed").

    Реальная структура HTML (верифицировано 19.02.2026):
      <article class="tender-row row" id="90147690">
        <a class="description tender-info__description tender-info__link"
           href="/region/.../90147690-tender-...">Заголовок</a>
        <div class="starting-price__price starting-price--price">445 000 ₽</div>
      </article>
    """
    tenders: list[dict[str, Any]] = []

    rows = await page.query_selector_all(S["tender_card"])
    if not rows:
        return tenders

    logger.debug(f"Карточек на странице: {len(rows)}")

    for row in rows:
        try:
            # Tender ID — атрибут id у <article>
            tender_id = await row.get_attribute("id")
            if not tender_id:
                continue

            # Ссылка и заголовок
            link_el = await row.query_selector(
                S["tender_link"]
            ) or await row.query_selector(S["tender_link_alt"])
            if not link_el:
                continue

            title = await link_el.inner_text()
            url = await link_el.get_attribute("href")
            if url and not url.startswith("http"):
                url = f"{BASE_URL}{url}"

            # Цена
            price_el = await row.query_selector(S["tender_price"])
            price_text = await price_el.inner_text() if price_el else "0"
            # Убираем всё кроме цифр и точки: "445 000 ₽" -> "445000"
            price = float(re.sub(r"[^\d.]", "", price_text.replace(",", ".")) or 0)

            tenders.append(
                {
                    "tender_id": tender_id,
                    "title": title.strip(),
                    "url": url,
                    "price": price,
                    "status": tender_status,
                }
            )
        except Exception as e:
            logger.error(f"Ошибка при парсинге карточки тендера: {e}")

    return tenders


# ── Публичные функции поиска ─────────────────────────────────────────────────


async def search_active_tenders(
    page: Page,
    *,
    keywords: list[str] | None = None,
    min_price: int = MIN_PRICE_ACTIVE,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """
    Выполняет поиск активных тендеров по фильтрам из ТЗ.
    Обходит все страницы пагинации.
    Возвращает список словарей с данными тендеров.

    Args:
        page: Playwright страница.
        keywords: Список ключевых слов для поиска.
        min_price: Минимальная цена.
        date_from: Дата начала поиска (DD.MM.YYYY).
        date_to: Дата окончания поиска (DD.MM.YYYY).
    """
    from src.config import SEARCH_KEYWORDS

    logger.info("Поиск активных тендеров на rostender.info...")

    effective_keywords = keywords if keywords is not None else SEARCH_KEYWORDS

    await _navigate_to_search(page)
    await _fill_common_filters(page, effective_keywords, min_price)

    # Дата публикации: из параметров или "сегодня"
    effective_date_from = date_from or datetime.now().strftime("%d.%m.%Y")
    effective_date_to = date_to or datetime.now().strftime("%d.%m.%Y")
    await page.fill(S["search_date_from"], effective_date_from)
    await page.fill(S["search_date_to"], effective_date_to)
    logger.debug("Фильтр дат: {} — {}", effective_date_from, effective_date_to)

    all_tenders = await _submit_and_collect(
        page,
        empty_warning="Результаты поиска не найдены",
    )

    logger.info(f"Итого найдено активных тендеров: {len(all_tenders)}")
    return all_tenders


async def extract_inn_from_page(page: Page, tender_url: str) -> str | None:
    """
    Переходит на страницу тендера и пытается извлечь ИНН заказчика.
    """
    await safe_goto(page, tender_url)
    await polite_wait()

    # Поиск ИНН в атрибуте 'inn' кнопки
    btn = await page.query_selector(S["inn_button"])
    if btn:
        inn = await btn.get_attribute("inn")
        if inn and inn.strip():
            return inn.strip()

    # Если в атрибуте нет, ищем в тексте страницы (ИНН: 1234567890)
    content = await page.content()
    inn_match = re.search(r"ИНН\s*:?\s*(\d{10,12})", content)
    if inn_match:
        return inn_match.group(1)

    # Попробуем найти ссылку на ЕИС (zakupki.gov.ru)
    eis_link_el = await page.query_selector(S["eis_link"])
    if eis_link_el:
        eis_url = await eis_link_el.get_attribute("href")
        logger.debug(
            f"Найдена ЕИС-ссылка: {eis_url} (фоллбэк не реализован, см. Шаг 5)"
        )

    logger.warning(f"ИНН не найден для тендера: {tender_url}")
    return None


async def get_customer_name(page: Page) -> str | None:
    """
    Извлекает название организации со страницы тендера.
    Вызывать после перехода на страницу тендера (extract_inn_from_page).
    """
    content = await page.content()

    # Ищем типичные формы названий организаций в кавычках
    name_match = re.search(
        r'(?:ООО|OAO.АО|пAO|ЗАО|MКУ|MБУ|ГБУ|ФГУП|ФГБУ|MУП|ГУП|ГБУЗ|BУ)\s+"[^"]+"',
        content,
    )
    if name_match:
        return name_match.group(0)

    # Альтернативный поиск: блок с заголовком "Организатор" или "Заказчик"
    name_match = re.search(
        r"(?:Организатор|Заказчик)[^<]*?<[^>]*>([^<]{5,100})</[^>]*>",
        content,
    )
    if name_match:
        return name_match.group(1).strip()

    return None


async def search_tenders_by_inn(
    page: Page,
    inn: str,
    *,
    keywords: list[str] | None = None,
    min_price: int = MIN_PRICE_RELATED,
) -> list[dict[str, Any]]:
    """
    Поиск активных тендеров конкретного заказчика по ИНН.

    Args:
        page: Playwright-страница.
        inn: ИНН заказчика.
        keywords: Список ключевых слов для поиска.
        min_price: Минимальная цена (по умолчанию 2M для расширенного поиска).

    Returns:
        Список словарей с данными тендеров.
    """
    from src.config import SEARCH_KEYWORDS

    logger.info(f"Поиск активных тендеров для ИНН {inn} (мин. цена: {min_price})...")

    effective_keywords = keywords if keywords is not None else SEARCH_KEYWORDS

    await _navigate_to_search(page)

    # ИНН заказчика (специфичное поле, только для этого варианта поиска)
    await page.fill(S["search_customers_input"], inn)

    await _fill_common_filters(page, effective_keywords, min_price)

    all_tenders = await _submit_and_collect(
        page,
        log_context=f"для ИНН {inn}",
        empty_warning=f"Тендеры для ИНН {inn} не найдены",
    )

    logger.info(f"Для ИНН {inn} найдено тендеров: {len(all_tenders)}")
    return all_tenders
