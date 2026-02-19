"""Модуль для поиска активных тендеров на rostender.info."""

import re
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from playwright.async_api import Page

from src.config import (
    EXCLUDE_KEYWORDS,
    MIN_PRICE_ACTIVE,
    SEARCH_KEYWORDS,
)
from src.scraper.browser import BASE_URL, polite_wait, safe_goto


async def search_active_tenders(page: Page) -> list[dict[str, Any]]:
    """
    Выполняет поиск активных тендеров по фильтрам из ТЗ.
    Возвращает список словарей с данными тендеров.
    """
    logger.info("Поиск активных тендеров на rostender.info...")

    # 1. Переходим на страницу расширенного поиска
    await safe_goto(page, f"{BASE_URL}/extsearch/advanced")

    # 2. Заполняем фильтры
    # Ключевые слова
    keywords_str = ", ".join(SEARCH_KEYWORDS)
    await page.fill("#keywords", keywords_str)

    # Исключения
    exclude_str = ", ".join(EXCLUDE_KEYWORDS)
    await page.fill("#exceptions", exclude_str)

    # Цена от (используем дисплейное поле, Playwright сам обработает маску или заполним скрытое)
    await page.fill("#min_price-disp", str(MIN_PRICE_ACTIVE))

    # Скрывать без цены
    await page.check("#hide_price")

    # Этап: Прием заявок (значение 10).
    # В расширенном поиске по умолчанию выбраны почти все, кроме планируемых.
    # Нам нужно убедиться, что выбрано только "Прием заявок".
    # Сначала снимем все, потом выберем нужный.
    # Поскольку это кастомный селект (Chosen), проще взаимодействовать с ним через evaluate
    await page.evaluate(
        """
        (val) => {
            const select = document.querySelector('#states');
            Array.from(select.options).forEach(opt => opt.selected = (opt.value == val));
            $(select).trigger('chosen:updated');
        }
    """,
        "10",
    )

    # Способ размещения (placement_ways): исключить Аукционы (1) и Ед. поставщик (28)
    # По умолчанию выбраны все.
    await page.evaluate(
        """
        (exclude_vals) => {
            const select = document.querySelector('#placement_ways');
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
        ["1", "28"],
    )

    # Дата: поиск за сегодня (как в ТЗ пример 10.02.2026 по 10.02.2026)
    # Для MVP установим текущую дату
    today = datetime.now().strftime("%d.%m.%Y")
    await page.fill("#tender-start-date-from", today)
    await page.fill("#tender-start-date-to", today)

    # 3. Нажимаем "Искать"
    await page.click("#start-search-button")
    await page.wait_for_load_state("networkidle")

    # 4. Собираем результаты
    tenders = []

    # Проверяем, есть ли результаты
    if await page.query_selector(".search-results") is None:
        logger.warning("Результаты поиска не найдены")
        return tenders

    # Собираем ссылки на тендеры со страницы результатов
    # На rostender.info карточки тендеров обычно имеют класс .tender-row или похожий
    # В результатах поиска это ссылки внутри .search-results__item или h2/h3
    rows = await page.query_selector_all(".tender-row")
    if not rows:
        # Альтернативный селектор для некоторых версий верстки
        rows = await page.query_selector_all(".search-results__item")

    logger.info(f"Найдено карточек на странице: {len(rows)}")

    for row in rows:
        try:
            link_el = await row.query_selector(
                "a.description"
            ) or await row.query_selector("a[href*='/tender/']")
            if not link_el:
                continue

            title = await link_el.inner_text()
            url = await link_el.get_attribute("href")
            if not url.startswith("http"):
                url = f"{BASE_URL}{url}"

            # Извлекаем ID из URL
            # Пример: /tender/89869707-...
            match = re.search(r"/tender/(\d+)", url)
            tender_id = match.group(1) if match else url.split("/")[-1].split("-")[0]

            # Цена
            price_el = await row.query_selector(
                ".tender-row__price"
            ) or await row.query_selector(".price")
            price_text = await price_el.inner_text() if price_el else "0"
            # Очистка цены от мусора
            price = float(re.sub(r"[^\d.]", "", price_text.replace(",", ".")) or 0)

            tenders.append(
                {
                    "tender_id": tender_id,
                    "title": title.strip(),
                    "url": url,
                    "price": price,
                    "status": "active",
                }
            )
        except Exception as e:
            logger.error(f"Ошибка при парсинге карточки тендера: {e}")

    return tenders


async def extract_inn_from_page(page: Page, tender_url: str) -> str | None:
    """
    Переходит на страницу тендера и пытается извлечь ИНН заказчика.
    """
    await safe_goto(page, tender_url)
    await polite_wait()

    # Поиск ИНН. Как выяснилось, он в атрибуте 'inn' кнопки .toggle-counterparty
    # Даже если он пустой для неавторизованных, мы попробуем найти его в тексте страницы
    # или через переход в 'Анализ заказчика'

    btn = await page.query_selector(".toggle-counterparty")
    if btn:
        inn = await btn.get_attribute("inn")
        if inn and inn.strip():
            return inn.strip()

    # Если в атрибуте нет, ищем в тексте страницы (ИНН: 1234567890)
    content = await page.content()
    inn_match = re.search(r"ИНН\s*:?\s*(\d{10,12})", content)
    if inn_match:
        return inn_match.group(1)

    # Попробуем найти ссылку на ЕИС (zakupki.gov.ru), там ИНН часто есть в URL или на странице
    eis_link_el = await page.query_selector("a[href*='zakupki.gov.ru']")
    if eis_link_el:
        eis_url = await eis_link_el.get_attribute("href")
        # В URL ЕИС часто есть regNumber, но не ИНН. Но это задел на будущее.
        pass

    logger.warning(f"ИНН не найден для тендера: {tender_url}")
    return None


async def get_customer_name(page: Page) -> str | None:
    """Извлекает название организации со страницы тендера."""
    # Ищем блок 'Организатор закупки'
    label_el = await page.get_by_text("Организатор закупки").first
    if label_el:
        # Название обычно в следующем элементе или в родителе
        # Но для неавторизованных там заглушка.
        # Попробуем найти любой текст, похожий на название (ООО, АО, МКУ...)
        content = await page.content()
        # Очень грубый поиск названия организации
        name_match = re.search(r'(?:ООО|АО|ПАО|МКУ|ГБУ|ФГУП)\s+"[^"]+"', content)
        if name_match:
            return name_match.group(0)
    return None
