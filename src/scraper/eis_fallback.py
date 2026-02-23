"""Фоллбэк на zakupki.gov.ru (ЕИС) для извлечения ИНН и протоколов.

Используется когда:
1. На rostender.info не удалось извлечь ИНН заказчика
2. На rostender.info нет протокола — пробуем получить его с ЕИС
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.async_api import Page

from src.config import DOWNLOADS_DIR, MIN_PRICE_HISTORICAL
from src.scraper.browser import polite_wait, safe_goto

EIS_BASE_URL = "https://zakupki.gov.ru"
EIS_SEARCH_URL = f"{EIS_BASE_URL}/epz/order/extendedsearch/rss.html"


async def extract_inn_from_eis(page: Page, eis_url: str) -> str | None:
    """Извлекает ИНН заказчика со страницы ЕИС.

    Args:
        page: Playwright-страница.
        eis_url: URL тендера на zakupki.gov.ru.

    Returns:
        ИНН заказчика или None, если не найден.
    """
    logger.info("Извлечение ИНН со страницы ЕИС: {}", eis_url)

    await safe_goto(page, eis_url)
    await polite_wait()

    content = await page.content()

    inn_match = re.search(r"ИНН\s*:?\s*(\d{10,12})", content)
    if inn_match:
        inn = inn_match.group(1)
        logger.debug("ИНН найден в контенте: {}", inn)
        return inn

    inn_el = await page.query_selector("[data-inn], [data-Inn], [data-INN]")
    if inn_el:
        inn = (
            await inn_el.get_attribute("data-inn")
            or await inn_el.get_attribute("data-Inn")
            or await inn_el.get_attribute("data-INN")
        )
        if inn:
            logger.debug("ИНН найден в атрибуте: {}", inn)
            return inn

    customer_block = await page.query_selector(
        ".customerInfo, .organizerInfo, .col-xs-12"
    )
    if customer_block:
        block_text = await customer_block.inner_text()
        inn_match = re.search(r"(\d{10,12})", block_text)
        if inn_match:
            inn = inn_match.group(1)
            logger.debug("ИНН найден в блоке заказчика: {}", inn)
            return inn

    logger.warning("ИНН не найден на странице ЕИС: {}", eis_url)
    return None


async def search_historical_tenders_on_eis(
    page: Page,
    customer_inn: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Ищет завершённые тендеры заказчика на zakupki.gov.ru.

    Args:
        page: Playwright-страница.
        customer_inn: ИНН заказчика.
        limit: Максимальное число результатов.

    Returns:
        Список словарей с данными тендеров:
        {
            "tender_id": str,
            "eis_url": str,
            "title": str,
            "price": float | None,
            "publish_date": str | None,
        }
    """
    logger.info("Поиск завершённых тендеров на ЕИС для ИНН {}", customer_inn)

    tenders: list[dict[str, Any]] = []

    search_url = f"{EIS_SEARCH_URL}?searchString={customer_inn}&morphology=on"
    await safe_goto(page, search_url)
    await polite_wait()

    results_container = await page.query_selector(".search-results, .registryEntries")
    if not results_container:
        logger.info("Результаты поиска на ЕИС не найдены")
        return tenders

    tender_cards = await results_container.query_selector_all(
        ".registryEntry, .search-result-row, article"
    )

    for card in tender_cards[:limit]:
        try:
            link_el = await card.query_selector("a[href*='order/view']")
            if not link_el:
                continue

            href = await link_el.get_attribute("href")
            if not href:
                continue

            tender_id_match = re.search(r"id=(\d+)", href)
            tender_id = tender_id_match.group(1) if tender_id_match else None

            title_el = await card.query_selector(".title, .name, h3, h4")
            title = await title_el.inner_text() if title_el else "Без названия"

            price_el = await card.query_selector(".price, .sum, [data-price]")
            price_text = await price_el.inner_text() if price_el else None
            price = None
            if price_text:
                price_clean = re.sub(r"[^\d.]", "", price_text.replace(",", "."))
                price = float(price_clean) if price_clean else None

            if price and price < MIN_PRICE_HISTORICAL:
                continue

            tenders.append(
                {
                    "tender_id": tender_id or href.split("=")[-1],
                    "eis_url": f"{EIS_BASE_URL}{href}"
                    if href.startswith("/")
                    else href,
                    "title": title.strip(),
                    "price": price,
                    "publish_date": None,
                }
            )

        except Exception as e:
            logger.error("Ошибка при парсинге карточки тендера ЕИС: {}", e)
            continue

    logger.info("Найдено тендеров на ЕИС: {}", len(tenders))
    return tenders


async def get_protocol_link_from_eis(
    page: Page,
    tender_eis_url: str,
) -> str | None:
    """Находит ссылку на протокол тендера на странице ЕИС.

    Args:
        page: Playwright-страница.
        tender_eis_url: URL тендера на zakupki.gov.ru.

    Returns:
        URL протокола или None.
    """
    await safe_goto(page, tender_eis_url)
    await polite_wait()

    protocol_links = await page.query_selector_all(
        "a[href*='protocol'], a[data-link*='protocol'], .protocol a"
    )

    for link in protocol_links:
        href = await link.get_attribute("href")
        if href and "protocol" in href.lower():
            if href.startswith("/"):
                return f"{EIS_BASE_URL}{href}"
            return href

    logger.debug("Протокол не найден на странице: {}", tender_eis_url)
    return None


async def download_protocol_from_eis(
    page: Page,
    protocol_url: str,
    tender_id: str,
    customer_inn: str,
) -> Path | None:
    """Скачивает файл протокола с ЕИС.

    Args:
        page: Playwright-страница.
        protocol_url: URL для скачивания протокола.
        tender_id: ID тендера.
        customer_inn: ИНН заказчика.

    Returns:
        Путь к скачанному файлу или None.
    """
    download_dir = DOWNLOADS_DIR / customer_inn / tender_id / "eis"
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with page.expect_download(timeout=60_000) as download_info:
            await page.goto(protocol_url)
            await page.wait_for_load_state("networkidle")

        download = await download_info.value

        filename = download.suggested_filename
        file_path = download_dir / filename

        await download.save_as(str(file_path))
        logger.info(
            "Скачан протокол ЕИС: {} ({} байт)",
            file_path.name,
            file_path.stat().st_size,
        )
        return file_path

    except Exception as e:
        logger.error("Ошибка скачивания протокола с ЕИС: {}", e)
        return None


async def fallback_extract_inn(page: Page, tender_url: str) -> str | None:
    """Фоллбэк для извлечения ИНН через ЕИС.

    Используется когда на rostender.info ИНН не найден в атрибуте.

    Args:
        page: Playwright-страница.
        tender_url: URL тендера на rostender.info.

    Returns:
        ИНН заказчика или None.
    """
    await safe_goto(page, tender_url)
    await polite_wait()

    eis_link_el = await page.query_selector("a[href*='zakupki.gov.ru']")
    if not eis_link_el:
        logger.debug("ЕИС-ссылка не найдена на странице тендера")
        return None

    eis_url = await eis_link_el.get_attribute("href")
    if not eis_url:
        return None

    return await extract_inn_from_eis(page, eis_url)


async def fallback_get_protocol(
    page: Page,
    tender_eis_url: str,
    tender_id: str,
    customer_inn: str,
) -> Path | None:
    """Фоллбэк для получения протокола с ЕИС.

    Используется когда на rostender.info протокол не найден.

    Args:
        page: Playwright-страница.
        tender_eis_url: URL тендера на zakupki.gov.ru.
        tender_id: ID тендера.
        customer_inn: ИНН заказчика.

    Returns:
        Путь к скачанному протоколу или None.
    """
    protocol_url = await get_protocol_link_from_eis(page, tender_eis_url)
    if not protocol_url:
        logger.debug("Протокол не найден на ЕИС")
        return None

    return await download_protocol_from_eis(page, protocol_url, tender_id, customer_inn)
