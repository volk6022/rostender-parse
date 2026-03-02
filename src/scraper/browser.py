"""Управление Playwright-браузером для скрейпинга rostender.info."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from loguru import logger

from src.config import PROXY_CONFIG, BASE_URL, DEFAULT_TIMEOUT, POLITE_DELAY


@asynccontextmanager
async def create_browser(
    *,
    headless: bool = False,
) -> AsyncGenerator[Browser, None]:
    """Запустить Chromium через Playwright.

    Usage::

        async with create_browser() as browser:
            async with create_page(browser) as page:
                await safe_goto(page, "https://rostender.info")
    """
    pw: Playwright = await async_playwright().start()
    try:
        launch_kwargs: dict = {"headless": headless}
        if PROXY_CONFIG:
            launch_kwargs["proxy"] = PROXY_CONFIG
        browser = await pw.chromium.launch(**launch_kwargs)
        logger.debug(
            "Chromium запущен (headless={}, proxy={})",
            headless,
            PROXY_CONFIG["server"] if PROXY_CONFIG else "нет",
        )
        try:
            yield browser
        finally:
            await browser.close()
            logger.debug("Chromium остановлен")
    finally:
        await pw.stop()


@asynccontextmanager
async def create_page(
    browser: Browser,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> AsyncGenerator[Page, None]:
    """Создать страницу с настроенным контекстом (UA, viewport, locale)."""
    context: BrowserContext = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="ru-RU",
    )
    page = await context.new_page()
    page.set_default_timeout(timeout)
    try:
        yield page
    finally:
        await context.close()


async def safe_goto(page: Page, url: str, retries: int = 3) -> None:
    """Переход по URL с ожиданием загрузки и повторными попытками.

    Стратегия:
      1. ``domcontentloaded`` (30 с) — быстрая и надёжная.
      2. При ошибке — сброс страницы (``about:blank``), пауза, повтор.
      3. На последней попытке — ``commit`` (минимальное ожидание).

    ``networkidle`` **не** используется: rostender.info часто имеет
    фоновые запросы (аналитика, websocket), из-за которых ``networkidle``
    зависает навсегда.
    """
    last_error = None
    for attempt in range(retries):
        try:
            logger.debug("Переход -> {} (attempt {}/{})", url, attempt + 1, retries)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            return
        except Exception as e:
            last_error = e
            logger.warning(
                "Ошибка перехода (attempt {}/{}): {}", attempt + 1, retries, e
            )
            if attempt < retries - 1:
                # Сбрасываем страницу, чтобы следующий goto начинался «с чистого листа»
                try:
                    await page.goto("about:blank", timeout=5_000)
                except Exception:
                    pass
                delay = 3 * (attempt + 1)  # 3 с, 6 с
                logger.debug("Повтор через {} сек...", delay)
                await asyncio.sleep(delay)
            continue
    raise last_error if last_error else Exception(f"Failed to navigate to {url}")


async def polite_wait() -> None:
    """Вежливая пауза между запросами."""
    await asyncio.sleep(POLITE_DELAY)
