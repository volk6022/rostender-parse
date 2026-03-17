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
    """Авторизация на ETP GPB.

    Поддерживает переход на id.etpgpb.ru (Единый Личный Кабинет).
    """
    creds = get_credentials("gpb")
    if not creds:
        logger.debug("Учетные данные для GPB не настроены")
        return False

    login_url = "https://new.etpgpb.ru/login"
    logger.info("Авторизация на ETP GPB...")

    try:
        await safe_goto(page, login_url)

        # Проверяем, не залогинены ли мы уже
        if await page.query_selector(
            "a[href*='logout'], .user-menu, button:has-text('Выйти')"
        ):
            logger.debug("Уже авторизованы на GPB")
            return True

        # Если нас редиректнуло на выбор продуктов или форму логина ЕЛК
        if "id.etpgpb.ru" in page.url:
            # Если это страница выбора (products), нажимаем "Вход"
            login_btn = await page.query_selector(
                "a:has-text('Вход'), button:has-text('Вход')"
            )
            if login_btn:
                await login_btn.click()
                await page.wait_for_load_state("networkidle")

        # Ждем появления полей ввода (они могут быть разными для старой и новой формы)
        selectors = [
            "input[name='login']",
            "input[name='username']",
            "#login",
            "input[type='text']",
        ]

        input_found = False
        for sel in selectors:
            try:
                await page.wait_for_selector(sel, timeout=5000)
                await page.fill(sel, creds["login"])
                input_found = True
                break
            except:
                continue

        if not input_found:
            raise RuntimeError("Не удалось найти поле логина на GPB")

        # Пароль
        pw_selectors = ["input[name='password']", "#password", "input[type='password']"]
        for sel in pw_selectors:
            try:
                await page.fill(sel, creds["password"])
                break
            except:
                continue

        # Клик по кнопке входа
        submit_btn = await page.query_selector(
            "button[type='submit'], .btn-primary, button:has-text('Войти')"
        )
        if submit_btn:
            await submit_btn.click()
        else:
            await page.keyboard.press("Enter")

        await page.wait_for_load_state("networkidle")

        # Финальная проверка
        if "id.etpgpb.ru" in page.url or "login" in page.url:
            # Проверяем наличие ошибок на странице
            error = await page.query_selector(".error, .alert-danger, .error-message")
            if error:
                logger.error("Ошибка GPB: {}", await error.inner_text())
                return False

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
