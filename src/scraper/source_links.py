"""Модуль для извлечения внешних ссылок на источники (ЕИС и др.)."""

from __future__ import annotations

import re
from loguru import logger
from playwright.async_api import Page

# Маппинг домен -> имя источника
SOURCE_DOMAINS: dict[str, str] = {
    "zakupki.gov.ru": "eis",
    "etpgpb.ru": "gpb",
    "rosatom.ru": "rosatom",
    "roseltorg.ru": "roseltorg",
}


async def extract_source_urls(page: Page) -> str | None:
    """Извлекает все внешние ссылки на источники со страницы тендера.
    Возвращает строку вида 'eis:https://...,gpb:https://...' или None.
    """
    try:
        # Извлекаем все href'ы атомарно через JS, чтобы избежать Stale Element Reference
        # при возможном force-reload страницы.
        hrefs = await page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.getAttribute('href'))"
        )
        if not hrefs:
            return None

        found_sources: dict[str, str] = {}

        for href in hrefs:
            if not href:
                continue

            for domain, source_name in SOURCE_DOMAINS.items():
                if domain in href:
                    # Сохраняем только одну ссылку на каждый источник (первую найденную)
                    if source_name not in found_sources:
                        found_sources[source_name] = href

        if not found_sources:
            return None

        # Форматируем в строку: name1:url1,name2:url2
        return ",".join(f"{name}:{url}" for name, url in found_sources.items())

    except Exception as e:
        if "Execution context was destroyed" in str(e):
            # Проглатываем ошибку контекста, т.к. при перегрузке страницы
            # мы можем либо попробовать еще раз (в вызывающем коде),
            # либо просто вернуть None.
            logger.debug(f"Контекст уничтожен при извлечении ссылок: {e}")
            return None
        logger.error(f"Ошибка при извлечении ссылок на источники: {e}")
        return None


def get_source_url(source_urls: str | None, source_name: str) -> str | None:
    """Извлекает URL конкретного источника из строки source_urls."""
    if not source_urls:
        return None

    # Ищем паттерн 'source_name:url'
    # Используем регулярку, чтобы корректно обработать запятые внутри URL (если они там есть)
    # Но обычно URL не содержат запятых, либо они заэкранированы.
    # Простейший сплит по запятой, затем поиск префикса.
    parts = source_urls.split(",")
    for part in parts:
        if part.startswith(f"{source_name}:"):
            return part[len(source_name) + 1 :]

    return None


def parse_source_urls(source_urls: str | None) -> dict[str, str]:
    """Парсит строку source_urls в словарь {name: url}."""
    if not source_urls:
        return {}

    result = {}
    parts = source_urls.split(",")
    for part in parts:
        if ":" in part:
            name, url = part.split(":", 1)
            result[name] = url
    return result
