"""Tests for src.scraper.auth — authentication on rostender.info."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Tests ────────────────────────────────────────────────────────────────────


class TestLogin:
    """Tests for the login() async function."""

    @pytest.mark.asyncio
    async def test_successful_login(self) -> None:
        """After submit, .header--notLogged not found → success."""
        page = AsyncMock()
        # query_selector returns None → user IS logged in
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch("src.scraper.auth.safe_goto", new_callable=AsyncMock) as mock_goto,
            patch("src.scraper.auth.polite_wait", new_callable=AsyncMock),
            patch("src.scraper.auth.BASE_URL", "https://rostender.info"),
            patch("src.scraper.auth.ROSTENDER_LOGIN", "user@test.com"),
            patch("src.scraper.auth.ROSTENDER_PASSWORD", "secret123"),
            patch(
                "src.scraper.auth.SELECTORS",
                {
                    "login_username": "#username",
                    "login_password": "#password",
                    "login_button": "button[name='login-button']",
                    "logged_in_marker": ".header--notLogged",
                },
            ),
        ):
            from src.scraper.auth import login

            await login(page)

        # Navigated to login page
        mock_goto.assert_called_once_with(page, "https://rostender.info/login")
        # Filled credentials
        page.fill.assert_any_call("#username", "user@test.com")
        page.fill.assert_any_call("#password", "secret123")
        # Clicked submit
        page.click.assert_called_once_with("button[name='login-button']")
        # Waited for DOM
        page.wait_for_load_state.assert_called_once_with("domcontentloaded")

    @pytest.mark.asyncio
    async def test_failed_login_raises_runtime_error(self) -> None:
        """When .header--notLogged is still present → RuntimeError."""
        page = AsyncMock()
        # query_selector returns a truthy element → user NOT logged in
        page.query_selector = AsyncMock(return_value=MagicMock())

        with (
            patch("src.scraper.auth.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.auth.polite_wait", new_callable=AsyncMock),
            patch("src.scraper.auth.BASE_URL", "https://rostender.info"),
            patch("src.scraper.auth.ROSTENDER_LOGIN", "user@test.com"),
            patch("src.scraper.auth.ROSTENDER_PASSWORD", "wrong"),
            patch(
                "src.scraper.auth.SELECTORS",
                {
                    "login_username": "#username",
                    "login_password": "#password",
                    "login_button": "button[name='login-button']",
                    "logged_in_marker": ".header--notLogged",
                },
            ),
        ):
            from src.scraper.auth import login

            with pytest.raises(RuntimeError, match="Авторизация.*не удалась"):
                await login(page)

    @pytest.mark.asyncio
    async def test_fills_correct_credentials_from_config(self) -> None:
        """Credentials from config are passed to page.fill()."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch("src.scraper.auth.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.auth.polite_wait", new_callable=AsyncMock),
            patch("src.scraper.auth.BASE_URL", "https://rostender.info"),
            patch("src.scraper.auth.ROSTENDER_LOGIN", "mylogin"),
            patch("src.scraper.auth.ROSTENDER_PASSWORD", "mypass"),
            patch(
                "src.scraper.auth.SELECTORS",
                {
                    "login_username": "#user-field",
                    "login_password": "#pass-field",
                    "login_button": "#submit-btn",
                    "logged_in_marker": ".not-logged",
                },
            ),
        ):
            from src.scraper.auth import login

            await login(page)

        page.fill.assert_any_call("#user-field", "mylogin")
        page.fill.assert_any_call("#pass-field", "mypass")

    @pytest.mark.asyncio
    async def test_polite_wait_called_twice(self) -> None:
        """polite_wait is called after goto and after form submit."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch("src.scraper.auth.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.auth.polite_wait", new_callable=AsyncMock) as mock_wait,
            patch("src.scraper.auth.BASE_URL", "https://rostender.info"),
            patch("src.scraper.auth.ROSTENDER_LOGIN", "u"),
            patch("src.scraper.auth.ROSTENDER_PASSWORD", "p"),
            patch(
                "src.scraper.auth.SELECTORS",
                {
                    "login_username": "#u",
                    "login_password": "#p",
                    "login_button": "#btn",
                    "logged_in_marker": ".marker",
                },
            ),
        ):
            from src.scraper.auth import login

            await login(page)

        assert mock_wait.call_count == 2

    @pytest.mark.asyncio
    async def test_checks_logged_in_marker_selector(self) -> None:
        """query_selector is called with the logged_in_marker selector."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch("src.scraper.auth.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.auth.polite_wait", new_callable=AsyncMock),
            patch("src.scraper.auth.BASE_URL", "https://rostender.info"),
            patch("src.scraper.auth.ROSTENDER_LOGIN", "u"),
            patch("src.scraper.auth.ROSTENDER_PASSWORD", "p"),
            patch(
                "src.scraper.auth.SELECTORS",
                {
                    "login_username": "#u",
                    "login_password": "#p",
                    "login_button": "#btn",
                    "logged_in_marker": ".custom-marker",
                },
            ),
        ):
            from src.scraper.auth import login

            await login(page)

        page.query_selector.assert_called_once_with(".custom-marker")
