"""Tests for src.scraper.browser — Playwright browser management."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Tests for safe_goto ──────────────────────────────────────────────────────


class TestSafeGoto:
    """Tests for the safe_goto() retry logic."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        """When domcontentloaded succeeds on first try, returns immediately."""
        page = AsyncMock()
        page.goto = AsyncMock(return_value=None)

        from src.scraper.browser import safe_goto

        await safe_goto(page, "https://example.com")

        page.goto.assert_called_once_with(
            "https://example.com", wait_until="domcontentloaded", timeout=30_000
        )

    @pytest.mark.asyncio
    async def test_retry_resets_page_with_about_blank(self) -> None:
        """On failure, navigates to about:blank before retrying."""
        page = AsyncMock()
        call_count = 0

        async def mock_goto(url: str, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("timeout")
            # about:blank (call 2) succeeds, retry (call 3) succeeds

        page.goto = mock_goto

        from src.scraper.browser import safe_goto

        with patch("src.scraper.browser.asyncio.sleep", new_callable=AsyncMock):
            await safe_goto(page, "https://example.com")

        # 1: main URL fail, 2: about:blank reset, 3: main URL success
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_failure(self) -> None:
        """When first attempt fails, retries after page reset."""
        page = AsyncMock()
        call_count = 0

        async def mock_goto(url: str, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("fail #1")
            # call 2 = about:blank, call 3 = retry succeeds

        page.goto = mock_goto

        from src.scraper.browser import safe_goto

        with patch("src.scraper.browser.asyncio.sleep", new_callable=AsyncMock):
            await safe_goto(page, "https://example.com")

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self) -> None:
        """After all retries exhausted, raises the last error."""
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("persistent failure"))

        from src.scraper.browser import safe_goto

        with patch("src.scraper.browser.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="persistent failure"):
                await safe_goto(page, "https://example.com")

    @pytest.mark.asyncio
    async def test_retries_parameter(self) -> None:
        """Custom retries parameter controls attempt count."""
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("fail"))

        from src.scraper.browser import safe_goto

        with patch("src.scraper.browser.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="fail"):
                await safe_goto(page, "https://example.com", retries=1)

        # 1 retry: domcontentloaded fails → no more retries (no about:blank for last attempt)
        assert page.goto.call_count == 1

    @pytest.mark.asyncio
    async def test_sleeps_between_retries_with_backoff(self) -> None:
        """On retry, sleeps with increasing delay (3s, 6s)."""
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("fail"))

        from src.scraper.browser import safe_goto

        with patch(
            "src.scraper.browser.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(Exception):
                await safe_goto(page, "https://example.com", retries=3)

        # Should sleep between retries (not after last attempt)
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [3, 6]  # 3 * (attempt+1)

    @pytest.mark.asyncio
    async def test_raises_generic_exception_when_no_last_error(self) -> None:
        """Edge case: retries=0 should raise a generic exception."""
        page = AsyncMock()

        from src.scraper.browser import safe_goto

        with pytest.raises(Exception, match="Failed to navigate"):
            await safe_goto(page, "https://example.com", retries=0)


# ── Tests for polite_wait ────────────────────────────────────────────────────


class TestPoliteWait:
    """Tests for the polite_wait() function."""

    @pytest.mark.asyncio
    async def test_calls_asyncio_sleep(self) -> None:
        """polite_wait calls asyncio.sleep with POLITE_DELAY."""
        with patch(
            "src.scraper.browser.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            from src.scraper.browser import polite_wait

            await polite_wait()

        mock_sleep.assert_called_once_with(2.0)

    @pytest.mark.asyncio
    async def test_uses_config_polite_delay(self) -> None:
        """polite_wait uses the POLITE_DELAY from config."""
        with (
            patch("src.scraper.browser.POLITE_DELAY", 5.0),
            patch(
                "src.scraper.browser.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
        ):
            from src.scraper.browser import polite_wait

            await polite_wait()

        mock_sleep.assert_called_once_with(5.0)


# ── Tests for create_browser ─────────────────────────────────────────────────


class TestCreateBrowser:
    """Tests for the create_browser() async context manager."""

    @pytest.mark.asyncio
    async def test_launches_chromium_headless_by_default(self) -> None:
        """create_browser launches Chromium with headless=True by default."""
        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.start = AsyncMock(return_value=mock_pw)

        with (
            patch(
                "src.scraper.browser.async_playwright",
                return_value=mock_playwright_cm,
            ),
            patch("src.scraper.browser.PROXY_CONFIG", None),
        ):
            from src.scraper.browser import create_browser

            async with create_browser() as browser:
                assert browser is mock_browser

        mock_pw.chromium.launch.assert_called_once_with(headless=True)
        mock_browser.close.assert_called_once()
        mock_pw.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_launches_with_headless_false(self) -> None:
        """create_browser(headless=False) passes headless=False to launch."""
        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.start = AsyncMock(return_value=mock_pw)

        with (
            patch(
                "src.scraper.browser.async_playwright",
                return_value=mock_playwright_cm,
            ),
            patch("src.scraper.browser.PROXY_CONFIG", None),
        ):
            from src.scraper.browser import create_browser

            async with create_browser(headless=False) as browser:
                pass

        launch_kwargs = mock_pw.chromium.launch.call_args[1]
        assert launch_kwargs["headless"] is False

    @pytest.mark.asyncio
    async def test_passes_proxy_config(self) -> None:
        """When PROXY_CONFIG is set, it is passed to chromium.launch."""
        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.start = AsyncMock(return_value=mock_pw)

        proxy = {"server": "http://proxy:8080", "username": "u", "password": "p"}

        with (
            patch(
                "src.scraper.browser.async_playwright",
                return_value=mock_playwright_cm,
            ),
            patch("src.scraper.browser.PROXY_CONFIG", proxy),
        ):
            from src.scraper.browser import create_browser

            async with create_browser() as browser:
                pass

        launch_kwargs = mock_pw.chromium.launch.call_args[1]
        assert launch_kwargs["proxy"] is proxy

    @pytest.mark.asyncio
    async def test_closes_browser_on_exception(self) -> None:
        """Browser is closed even if an exception occurs inside the context."""
        mock_browser = AsyncMock()
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_playwright_cm = AsyncMock()
        mock_playwright_cm.start = AsyncMock(return_value=mock_pw)

        with (
            patch(
                "src.scraper.browser.async_playwright",
                return_value=mock_playwright_cm,
            ),
            patch("src.scraper.browser.PROXY_CONFIG", None),
        ):
            from src.scraper.browser import create_browser

            with pytest.raises(ValueError, match="test error"):
                async with create_browser() as browser:
                    raise ValueError("test error")

        mock_browser.close.assert_called_once()
        mock_pw.stop.assert_called_once()


# ── Tests for create_page ────────────────────────────────────────────────────


class TestCreatePage:
    """Tests for the create_page() async context manager."""

    @pytest.mark.asyncio
    async def test_creates_context_and_page(self) -> None:
        """create_page creates a new context and page with correct settings."""
        # set_default_timeout is sync in Playwright, so use MagicMock for it
        mock_page = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        from src.scraper.browser import create_page

        async with create_page(mock_browser) as page:
            assert page is mock_page

        # Verify context was created with correct params
        ctx_kwargs = mock_browser.new_context.call_args[1]
        assert ctx_kwargs["viewport"] == {"width": 1280, "height": 900}
        assert ctx_kwargs["locale"] == "ru-RU"
        assert "Mozilla" in ctx_kwargs["user_agent"]

        # Verify default timeout was set
        mock_page.set_default_timeout.assert_called_once()

        # Verify context was closed
        mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_timeout(self) -> None:
        """create_page respects custom timeout parameter."""
        mock_page = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        from src.scraper.browser import create_page

        async with create_page(mock_browser, timeout=30000) as page:
            pass

        mock_page.set_default_timeout.assert_called_once_with(30000)

    @pytest.mark.asyncio
    async def test_closes_context_on_exception(self) -> None:
        """Context is closed even if an exception occurs inside."""
        mock_page = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        from src.scraper.browser import create_page

        with pytest.raises(RuntimeError, match="page error"):
            async with create_page(mock_browser) as page:
                raise RuntimeError("page error")

        mock_context.close.assert_called_once()
