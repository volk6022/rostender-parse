"""Модуль для поиска активных тендеров на rostender.info."""

import re
from datetime import datetime
from typing import Any

from loguru import logger
from playwright.async_api import Page

from src.config import (
    EXCLUDE_KEYWORDS,
    MIN_PRICE_ACTIVE,
    SEARCH_DATE_FROM,
    SEARCH_DATE_TO,
    SEARCH_KEYWORDS,
    SELECTORS,
)
from src.scraper.browser import BASE_URL, polite_wait, safe_goto

# Короткий алиас для читаемости.
S = SELECTORS


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


async def search_active_tenders(page: Page) -> list[dict[str, Any]]:
    """
    Выполняет поиск активных тендеров по фильтрам из ТЗ.
    Обходит все страницы пагинации.
    Возвращает список словарей с данными тендеров.
    """
    logger.info("Поиск активных тендеров на rostender.info...")

    # 1. Переходим на страницу расширенного поиска
    await safe_goto(page, f"{BASE_URL}/extsearch/advanced")

    # 2. Заполняем фильтры
    # Ключевые слова
    keywords_str = ", ".join(SEARCH_KEYWORDS)
    await page.fill(S["search_keywords_input"], keywords_str)

    # Исключения
    exclude_str = ", ".join(EXCLUDE_KEYWORDS)
    await page.fill(S["search_exceptions_input"], exclude_str)

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
        [str(MIN_PRICE_ACTIVE), S["search_min_price"], S["search_min_price_disp"]],
    )

    # Скрывать без цены
    await page.check(S["search_hide_price"])

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

    # Дата публикации: из конфига или «сегодня»
    date_from = SEARCH_DATE_FROM or datetime.now().strftime("%d.%m.%Y")
    date_to = SEARCH_DATE_TO or datetime.now().strftime("%d.%m.%Y")
    await page.fill(S["search_date_from"], date_from)
    await page.fill(S["search_date_to"], date_to)
    logger.debug("Фильтр дат: {} — {}", date_from, date_to)

    # 3. Нажимаем "Искать"
    await page.click(S["search_button"])
    await page.wait_for_load_state("networkidle")

    # 4. Собираем результаты со всех страниц (пагинация)
    all_tenders: list[dict[str, Any]] = []
    page_num = 1

    while True:
        logger.info(f"Парсинг страницы результатов #{page_num}...")

        # Проверяем, есть ли карточки тендеров на странице
        rows = await page.query_selector_all(S["tender_card"])
        if not rows:
            if page_num == 1:
                logger.warning("Результаты поиска не найдены")
            break

        # Парсим текущую страницу
        page_tenders = await parse_tenders_on_page(page)
        all_tenders.extend(page_tenders)
        logger.info(
            f"Страница {page_num}: найдено {len(page_tenders)} тендеров "
            f"(всего: {len(all_tenders)})"
        )

        # Проверяем наличие кнопки "Следующая"
        next_btn = await page.query_selector(S["pagination_next"])
        if not next_btn:
            logger.debug("Следующей страницы нет — пагинация завершена")
            break

        # Переходим на следующую страницу
        await next_btn.click()
        await page.wait_for_load_state("networkidle")
        await polite_wait()
        page_num += 1

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
    # TODO: Шаг 5 (eis_fallback.py) — реализовать переход по ссылке ЕИС
    # для извлечения ИНН и протоколов с zakupki.gov.ru.
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
        r'(?:ООО|ОАО|АО|ПАО|ЗАО|МКУ|МБУ|ГБУ|ФГУП|ФГБУ|МУП|ГУП|ГБУЗ|БУ)\s+"[^"]+"',
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
