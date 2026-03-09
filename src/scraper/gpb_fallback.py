"""Фоллбэк для ETP GPB (new.etpgpb.ru)."""

from __future__ import annotations

from pathlib import Path
from loguru import logger
from playwright.async_api import Page

from src.config import DOWNLOADS_DIR
from src.scraper.browser import polite_wait, safe_goto
from src.scraper.auth import login_to_gpb


async def extract_inn_from_gpb(page: Page, url: str) -> str | None:
    """Извлекает ИНН заказчика со страницы тендера GPB."""
    logger.info("Извлечение ИНН с GPB: {}", url)
    await safe_goto(page, url)
    await polite_wait()

    # Пытаемся найти ИНН через JS
    inn = await page.evaluate("""
        () => {
            const text = document.body.innerText;
            const match = text.match(/ИНН\\s*:?\\s*(\\d{10,12})/);
            return match ? match[1] : null;
        }
    """)
    return inn


async def get_protocol_links_from_gpb(page: Page, url: str) -> list[str]:
    """Ищет ссылки на протоколы на GPB."""
    await safe_goto(page, url)
    await polite_wait()

    links = await page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href*="protocol"], a[href*="протокол"]'))
                  .map(a => a.href)
    """)
    return list(set(links))


async def download_protocol_from_gpb(
    page: Page, url: str, tender_id: str, customer_inn: str
) -> Path | None:
    """Скачивает протокол с GPB."""
    # Попытка входа если нужно (GPB часто требует логина для файлов)
    await login_to_gpb(page)

    save_dir = DOWNLOADS_DIR / customer_inn / tender_id / "gpb"
    save_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Если это ссылка на PDF/DOCX, пробуем скачать напрямую
        # Но GPB часто отдает файлы через редирект или кнопку
        async with page.expect_download(timeout=60_000) as download_info:
            await page.goto(url)
        download = await download_info.value
        file_path = save_dir / download.suggested_filename
        await download.save_as(str(file_path))
        return file_path
    except Exception as e:
        logger.debug(
            "expect_download на GPB не сработал ({}), пробуем через evaluate click", e
        )
        try:
            # Находим ссылку и кликаем
            async with page.expect_download(timeout=60_000) as download_info:
                await page.evaluate(
                    f'(u) => {{ const a = document.querySelector(`a[href="${{u}}"]`); if (a) a.click(); else window.location.href = u; }}',
                    url,
                )
            download = await download_info.value
            file_path = save_dir / download.suggested_filename
            await download.save_as(str(file_path))
            return file_path
        except Exception as e2:
            logger.error("Ошибка скачивания с GPB: {}", e2)
            return None
