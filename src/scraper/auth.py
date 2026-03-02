"""Авторизация на rostender.info через Playwright."""

from __future__ import annotations

from playwright.async_api import Page
from loguru import logger

from src.config import ROSTENDER_LOGIN, ROSTENDER_PASSWORD, SELECTORS, BASE_URL
from src.scraper.browser import safe_goto, polite_wait


async def login(page: Page) -> None:
    """Выполнить авторизацию на rostender.info.

    Переходит на страницу логина, заполняет форму,
    отправляет и проверяет успешность входа.

    Raises:
        RuntimeError: если авторизация не удалась.
    """
    login_url = f"{BASE_URL}/login"
    logger.info("Авторизация на rostender.info...")

    await safe_goto(page, login_url)
    await polite_wait()

    # Заполняем форму
    await page.fill(SELECTORS["login_username"], ROSTENDER_LOGIN)
    await page.fill(SELECTORS["login_password"], ROSTENDER_PASSWORD)

    # Отправляем форму
    await page.click(SELECTORS["login_button"])
    await page.wait_for_load_state("domcontentloaded")
    await polite_wait()

    # Проверяем успешность входа:
    # Класс .header--notLogged присутствует только у неавторизованных пользователей.
    # Если он всё ещё есть после отправки формы — логин не удался.
    not_logged = await page.query_selector(SELECTORS["logged_in_marker"])
    if not_logged:
        raise RuntimeError(
            "Авторизация на rostender.info не удалась. "
            "Проверьте rostender_login и rostender_password в config.yaml"
        )

    logger.success("Авторизация на rostender.info успешна")


async def ensure_logged_in(page: Page) -> None:
    """Проверить сессию и повторно авторизоваться при необходимости.

    Переходит на главную страницу и проверяет маркер авторизации.
    Если сессия истекла — вызывает :func:`login` повторно.

    Безопасно вызывать часто: если сессия активна, выполняется быстро.
    """
    try:
        await safe_goto(page, BASE_URL)
        not_logged = await page.query_selector(SELECTORS["logged_in_marker"])
        if not_logged:
            logger.warning("Сессия истекла — повторная авторизация...")
            await login(page)
        else:
            logger.debug("Сессия активна")
    except Exception as exc:
        logger.warning("Ошибка проверки сессии ({}), пробуем re-login...", exc)
        await login(page)
