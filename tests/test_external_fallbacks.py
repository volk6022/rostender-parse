"""Tests for external fallback modules (GPB, Rosatom, Roseltorg)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import Page


# ── GPB Fallback Tests ───────────────────────────────────────────────────────


class TestGpbFallback:
    @pytest.mark.asyncio
    async def test_extract_inn_from_gpb(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="1234567890")

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.gpb.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import extract_inn_from_gpb

            result = await extract_inn_from_gpb(page, "https://new.etpgpb.ru/tender/1")

        assert result == "1234567890"

    @pytest.mark.asyncio
    async def test_get_protocol_links_from_gpb(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(
            return_value=["https://gpb.ru/proto1", "https://gpb.ru/proto2"]
        )

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.gpb.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import get_protocol_links_from_gpb

            result = await get_protocol_links_from_gpb(
                page, "https://new.etpgpb.ru/tender/1"
            )

        assert len(result) == 2
        assert "https://gpb.ru/proto1" in result

    @pytest.mark.asyncio
    async def test_download_protocol_from_gpb_success(self, tmp_path: Path) -> None:
        page = AsyncMock(spec=Page)

        mock_download = MagicMock()
        mock_download.suggested_filename = "gpb_proto.pdf"
        mock_download.save_as = AsyncMock()

        async def _get_download():
            return mock_download

        class FakeEventInfo:
            def __init__(self):
                self.value = _get_download()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        page.expect_download = MagicMock(return_value=FakeEventInfo())

        with (
            patch("src.scraper.fallbacks.gpb.DOWNLOADS_DIR", tmp_path),
            patch("src.scraper.fallbacks.gpb.login_to_gpb", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import download_protocol_from_gpb

            result = await download_protocol_from_gpb(
                page, "https://gpb.ru/proto", "T1", "INN1"
            )

        assert result is not None
        assert result.name == "gpb_proto.pdf"


# ── Rosatom Fallback Tests ───────────────────────────────────────────────────


class TestRosatomFallback:
    @pytest.mark.asyncio
    async def test_extract_inn_from_rosatom(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="7700000000")

        with (
            patch("src.scraper.fallbacks.rosatom.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.rosatom.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.rosatom import extract_inn_from_rosatom

            result = await extract_inn_from_rosatom(
                page, "https://zakupki.rosatom.ru/1"
            )

        assert result == "7700000000"

    @pytest.mark.asyncio
    async def test_download_protocol_from_rosatom(self, tmp_path: Path) -> None:
        page = AsyncMock(spec=Page)
        mock_download = MagicMock()
        mock_download.suggested_filename = "rosatom.pdf"
        mock_download.save_as = AsyncMock()

        async def _get_download():
            return mock_download

        class FakeEventInfo:
            def __init__(self):
                self.value = _get_download()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        page.expect_download = MagicMock(return_value=FakeEventInfo())

        with patch("src.scraper.fallbacks.rosatom.DOWNLOADS_DIR", tmp_path):
            from src.scraper.fallbacks.rosatom import download_protocol_from_rosatom

            result = await download_protocol_from_rosatom(
                page, "https://rosatom.ru/p", "T1", "INN1"
            )

        assert result is not None
        assert result.name == "rosatom.pdf"


# ── Roseltorg Fallback Tests ─────────────────────────────────────────────────


class TestRoseltorgFallback:
    @pytest.mark.asyncio
    async def test_extract_inn_from_roseltorg(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="7711223344")

        with (
            patch("src.scraper.fallbacks.roseltorg.safe_goto", new_callable=AsyncMock),
            patch(
                "src.scraper.fallbacks.roseltorg.polite_wait", new_callable=AsyncMock
            ),
        ):
            from src.scraper.fallbacks.roseltorg import extract_inn_from_roseltorg

            result = await extract_inn_from_roseltorg(page, "https://roseltorg.ru/1")

        assert result == "7711223344"
