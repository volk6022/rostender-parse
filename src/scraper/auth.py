"""Авторизация на rostender.info через Playwright."""

from __future__ import annotations

from playwright.async_api import Page
from loguru import logger

from src.config import (
    ROSTENDER_LOGIN,
    ROSTENDER_PASSWORD,
    SELECTORS,
    BASE_URL,
    get_credentials,
)
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


async def login_to_gpb(page: Page) -> bool:
    """Авторизация на ETP GPB."""
    creds = get_credentials("gpb")
    if not creds:
        logger.debug("Учетные данные для GPB не настроены")
        return False

    login_url = "https://new.etpgpb.ru/login"
    logger.info("Авторизация на ETP GPB...")

    try:
        await safe_goto(page, login_url)
        await page.fill("input[name='login'], #login", creds["login"])
        await page.fill("input[name='password'], #password", creds["password"])
        await page.click("button[type='submit'], .btn-primary")
        await page.wait_for_load_state("networkidle")
        logger.success("Авторизация на ETP GPB выполнена")
        return True
    except Exception as e:
        logger.error("Ошибка при входе на GPB: {}", e)
        return False


async def login_to_rosatom(page: Page) -> bool:
    """Авторизация на Zakupki Rosatom."""
    creds = get_credentials("rosatom")
    if not creds:
        return False

    login_url = "https://zakupki.rosatom.ru/web/login"
    logger.info("Авторизация на Zakupki Rosatom...")

    try:
        await safe_goto(page, login_url)
        await page.fill("#login", creds["login"])
        await page.fill("#password", creds["password"])
        await page.click("#login-button")
        await page.wait_for_load_state("networkidle")
        return True
    except Exception as e:
        logger.error("Ошибка при входе на Rosatom: {}", e)
        return False


async def login_to_roseltorg(page: Page) -> bool:
    """Авторизация на Roseltorg."""
    creds = get_credentials("roseltorg")
    if not creds:
        return False

    login_url = "https://www.roseltorg.ru/user/login"
    logger.info("Авторизация на Roseltorg...")

    try:
        await safe_goto(page, login_url)
        await page.fill("#login", creds["login"])
        await page.fill("#password", creds["password"])
        await page.click(".btn-submit")
        await page.wait_for_load_state("networkidle")
        return True
    except Exception as e:
        logger.error("Ошибка при входе на Roseltorg: {}", e)
        return False


async def login_to_eis(page: Page) -> bool:
    """Авторизация на EIS (zakupki.gov.ru)."""
    creds = get_credentials("eis")
    if not creds:
        return False

    login_url = "https://zakupki.gov.ru/epz/main/public/login.html"
    logger.info("Авторизация на EIS...")

    try:
        await safe_goto(page, login_url)
        # EIS имеет сложную структуру входа, часто через ЕСИА.
        # Здесь базовый пример, который может требовать уточнения селекторов.
        await page.fill("#login", creds["login"])
        await page.fill("#password", creds["password"])
        await page.click(".btn-login")
        await page.wait_for_load_state("networkidle")
        return True
    except Exception as e:
        logger.warning("Ошибка при входе на EIS (может быть публичный доступ): {}", e)
        return False
