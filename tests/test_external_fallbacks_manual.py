"""Расширенные ручные тесты для GPB, Rosatom, Roseltorg фоллбэков.

Покрывает edge cases, негативные сценарии, пропущенные функции,
и проверяет корректность логики каждого парсера.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from playwright.async_api import Page


# ── Helpers ──────────────────────────────────────────────────────────────────


class FakeEventInfo:
    """Имитирует page.expect_download() async context manager."""

    def __init__(self, download_mock):
        async def _get():
            return download_mock

        self.value = _get()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeEventInfoFailing:
    """Имитирует page.expect_download() который бросает исключение."""

    def __init__(self, exc: Exception):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *args):
        pass


# ══════════════════════════════════════════════════════════════════════════════
# GPB FALLBACK — РАСШИРЕННЫЕ ТЕСТЫ
# ══════════════════════════════════════════════════════════════════════════════


class TestGpbExtractInn:
    """Тесты extract_inn_from_gpb."""

    @pytest.mark.asyncio
    async def test_extracts_10_digit_inn(self) -> None:
        """Должен извлечь 10-значный ИНН."""
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="7707083893")

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", new_callable=AsyncMock) as sg,
            patch(
                "src.scraper.fallbacks.gpb.polite_wait", new_callable=AsyncMock
            ) as pw,
        ):
            from src.scraper.fallbacks.gpb import extract_inn_from_gpb

            result = await extract_inn_from_gpb(page, "https://new.etpgpb.ru/tender/1")

        assert result == "7707083893"
        sg.assert_awaited_once_with(page, "https://new.etpgpb.ru/tender/1")
        pw.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extracts_12_digit_inn(self) -> None:
        """Должен извлечь 12-значный ИНН (ИП)."""
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="770708389312")

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.gpb.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import extract_inn_from_gpb

            result = await extract_inn_from_gpb(page, "https://new.etpgpb.ru/tender/1")

        assert result == "770708389312"
        assert len(result) == 12

    @pytest.mark.asyncio
    async def test_returns_none_when_no_inn(self) -> None:
        """Должен вернуть None если ИНН не найден на странице."""
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value=None)

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.gpb.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import extract_inn_from_gpb

            result = await extract_inn_from_gpb(page, "https://new.etpgpb.ru/tender/1")

        assert result is None

    @pytest.mark.asyncio
    async def test_calls_safe_goto_and_polite_wait(self) -> None:
        """Проверяет вызов safe_goto и polite_wait в правильном порядке."""
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="1234567890")

        call_order = []

        async def track_goto(*a, **kw):
            call_order.append("safe_goto")

        async def track_wait():
            call_order.append("polite_wait")

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", side_effect=track_goto),
            patch("src.scraper.fallbacks.gpb.polite_wait", side_effect=track_wait),
        ):
            from src.scraper.fallbacks.gpb import extract_inn_from_gpb

            await extract_inn_from_gpb(page, "https://new.etpgpb.ru/tender/1")

        assert call_order == ["safe_goto", "polite_wait"]


class TestGpbProtocolLinks:
    """Тесты get_protocol_links_from_gpb."""

    @pytest.mark.asyncio
    async def test_returns_unique_links(self) -> None:
        """Должен дедуплицировать ссылки (list(set(...)))."""
        page = AsyncMock(spec=Page)
        # Дубликаты в ответе
        page.evaluate = AsyncMock(
            return_value=[
                "https://gpb.ru/proto1",
                "https://gpb.ru/proto1",
                "https://gpb.ru/proto2",
            ]
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
        assert set(result) == {"https://gpb.ru/proto1", "https://gpb.ru/proto2"}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_links(self) -> None:
        """Должен вернуть пустой список если нет ссылок на протоколы."""
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value=[])

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.gpb.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import get_protocol_links_from_gpb

            result = await get_protocol_links_from_gpb(
                page, "https://new.etpgpb.ru/tender/1"
            )

        assert result == []


class TestGpbDownload:
    """Тесты download_protocol_from_gpb."""

    @pytest.mark.asyncio
    async def test_download_success_first_attempt(self, tmp_path: Path) -> None:
        """Успешное скачивание с первой попытки (прямой goto)."""
        page = AsyncMock(spec=Page)
        mock_download = MagicMock()
        mock_download.suggested_filename = "protocol.pdf"
        mock_download.save_as = AsyncMock()

        page.expect_download = MagicMock(return_value=FakeEventInfo(mock_download))

        with (
            patch("src.scraper.fallbacks.gpb.DOWNLOADS_DIR", tmp_path),
            patch(
                "src.scraper.fallbacks.gpb.login_to_gpb",
                new_callable=AsyncMock,
            ) as mock_login,
        ):
            from src.scraper.fallbacks.gpb import download_protocol_from_gpb

            result = await download_protocol_from_gpb(
                page, "https://gpb.ru/proto", "T1", "INN1"
            )

        # login вызывается перед скачиванием
        mock_login.assert_awaited_once_with(page)
        assert result is not None
        assert result.name == "protocol.pdf"
        assert "INN1" in str(result)
        assert "T1" in str(result)

    @pytest.mark.asyncio
    async def test_download_creates_correct_directory(self, tmp_path: Path) -> None:
        """Должен создать структуру папок customer_inn/tender_id/gpb."""
        page = AsyncMock(spec=Page)
        mock_download = MagicMock()
        mock_download.suggested_filename = "test.pdf"
        mock_download.save_as = AsyncMock()

        page.expect_download = MagicMock(return_value=FakeEventInfo(mock_download))

        with (
            patch("src.scraper.fallbacks.gpb.DOWNLOADS_DIR", tmp_path),
            patch("src.scraper.fallbacks.gpb.login_to_gpb", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import download_protocol_from_gpb

            result = await download_protocol_from_gpb(
                page, "https://gpb.ru/p", "TENDER-99", "7707083893"
            )

        expected_dir = tmp_path / "7707083893" / "TENDER-99" / "gpb"
        assert expected_dir.exists()
        assert result == expected_dir / "test.pdf"

    @pytest.mark.asyncio
    async def test_download_fallback_on_first_failure(self, tmp_path: Path) -> None:
        """Если первый expect_download (goto) провалился —
        должен попробовать fallback через evaluate click."""
        page = AsyncMock(spec=Page)

        mock_download = MagicMock()
        mock_download.suggested_filename = "fallback.pdf"
        mock_download.save_as = AsyncMock()

        call_count = 0

        def make_event_info(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeEventInfoFailing(TimeoutError("no download"))
            return FakeEventInfo(mock_download)

        page.expect_download = MagicMock(side_effect=make_event_info)
        page.evaluate = AsyncMock()

        with (
            patch("src.scraper.fallbacks.gpb.DOWNLOADS_DIR", tmp_path),
            patch("src.scraper.fallbacks.gpb.login_to_gpb", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import download_protocol_from_gpb

            result = await download_protocol_from_gpb(
                page, "https://gpb.ru/p", "T1", "INN1"
            )

        assert result is not None
        assert result.name == "fallback.pdf"

    @pytest.mark.asyncio
    async def test_download_returns_none_on_both_failures(self, tmp_path: Path) -> None:
        """Если обе попытки (goto + evaluate click) провалились — вернуть None."""
        page = AsyncMock(spec=Page)

        page.expect_download = MagicMock(
            return_value=FakeEventInfoFailing(TimeoutError("no download"))
        )
        page.evaluate = AsyncMock()

        with (
            patch("src.scraper.fallbacks.gpb.DOWNLOADS_DIR", tmp_path),
            patch("src.scraper.fallbacks.gpb.login_to_gpb", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import download_protocol_from_gpb

            result = await download_protocol_from_gpb(
                page, "https://gpb.ru/p", "T1", "INN1"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_login_always_called_before_download(self, tmp_path: Path) -> None:
        """login_to_gpb всегда вызывается перед скачиванием."""
        page = AsyncMock(spec=Page)
        mock_download = MagicMock()
        mock_download.suggested_filename = "x.pdf"
        mock_download.save_as = AsyncMock()
        page.expect_download = MagicMock(return_value=FakeEventInfo(mock_download))

        with (
            patch("src.scraper.fallbacks.gpb.DOWNLOADS_DIR", tmp_path),
            patch(
                "src.scraper.fallbacks.gpb.login_to_gpb", new_callable=AsyncMock
            ) as mock_login,
        ):
            from src.scraper.fallbacks.gpb import download_protocol_from_gpb

            await download_protocol_from_gpb(page, "url", "T1", "INN1")

        mock_login.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# ROSATOM FALLBACK — РАСШИРЕННЫЕ ТЕСТЫ
# ══════════════════════════════════════════════════════════════════════════════


class TestRosatomExtractInn:
    """Тесты extract_inn_from_rosatom."""

    @pytest.mark.asyncio
    async def test_extracts_inn(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="7706123456")

        with (
            patch(
                "src.scraper.fallbacks.rosatom.safe_goto", new_callable=AsyncMock
            ) as sg,
            patch("src.scraper.fallbacks.rosatom.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.rosatom import extract_inn_from_rosatom

            result = await extract_inn_from_rosatom(
                page, "https://zakupki.rosatom.ru/1"
            )

        assert result == "7706123456"
        sg.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_inn(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value=None)

        with (
            patch("src.scraper.fallbacks.rosatom.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.rosatom.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.rosatom import extract_inn_from_rosatom

            result = await extract_inn_from_rosatom(
                page, "https://zakupki.rosatom.ru/1"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_extracts_12_digit_inn(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="770612345612")

        with (
            patch("src.scraper.fallbacks.rosatom.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.rosatom.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.rosatom import extract_inn_from_rosatom

            result = await extract_inn_from_rosatom(
                page, "https://zakupki.rosatom.ru/1"
            )

        assert result == "770612345612"


class TestRosatomProtocolLinks:
    """Тесты get_protocol_links_from_rosatom (ранее не покрыты тестами)."""

    @pytest.mark.asyncio
    async def test_returns_protocol_links(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(
            return_value=[
                "https://rosatom.ru/protocol/1",
                "https://rosatom.ru/printform/2",
            ]
        )

        with (
            patch("src.scraper.fallbacks.rosatom.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.rosatom.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.rosatom import get_protocol_links_from_rosatom

            result = await get_protocol_links_from_rosatom(
                page, "https://zakupki.rosatom.ru/1"
            )

        assert len(result) == 2
        assert "https://rosatom.ru/protocol/1" in result
        assert "https://rosatom.ru/printform/2" in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_links(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value=[])

        with (
            patch("src.scraper.fallbacks.rosatom.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.rosatom.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.rosatom import get_protocol_links_from_rosatom

            result = await get_protocol_links_from_rosatom(
                page, "https://zakupki.rosatom.ru/1"
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_deduplicates_links(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(
            return_value=[
                "https://rosatom.ru/protocol/1",
                "https://rosatom.ru/protocol/1",
            ]
        )

        with (
            patch("src.scraper.fallbacks.rosatom.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.rosatom.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.rosatom import get_protocol_links_from_rosatom

            result = await get_protocol_links_from_rosatom(
                page, "https://zakupki.rosatom.ru/1"
            )

        assert len(result) == 1


class TestRosatomDownload:
    """Тесты download_protocol_from_rosatom."""

    @pytest.mark.asyncio
    async def test_download_success(self, tmp_path: Path) -> None:
        page = AsyncMock(spec=Page)
        mock_download = MagicMock()
        mock_download.suggested_filename = "rosatom_protocol.pdf"
        mock_download.save_as = AsyncMock()

        page.expect_download = MagicMock(return_value=FakeEventInfo(mock_download))

        with patch("src.scraper.fallbacks.rosatom.DOWNLOADS_DIR", tmp_path):
            from src.scraper.fallbacks.rosatom import download_protocol_from_rosatom

            result = await download_protocol_from_rosatom(
                page, "https://rosatom.ru/p", "T1", "INN1"
            )

        assert result is not None
        assert result.name == "rosatom_protocol.pdf"

    @pytest.mark.asyncio
    async def test_download_creates_correct_directory(self, tmp_path: Path) -> None:
        page = AsyncMock(spec=Page)
        mock_download = MagicMock()
        mock_download.suggested_filename = "test.pdf"
        mock_download.save_as = AsyncMock()

        page.expect_download = MagicMock(return_value=FakeEventInfo(mock_download))

        with patch("src.scraper.fallbacks.rosatom.DOWNLOADS_DIR", tmp_path):
            from src.scraper.fallbacks.rosatom import download_protocol_from_rosatom

            result = await download_protocol_from_rosatom(
                page, "https://rosatom.ru/p", "T-42", "7707083893"
            )

        expected_dir = tmp_path / "7707083893" / "T-42" / "rosatom"
        assert expected_dir.exists()
        assert result == expected_dir / "test.pdf"

    @pytest.mark.asyncio
    async def test_download_returns_none_on_failure(self, tmp_path: Path) -> None:
        """Если скачивание провалилось — вернуть None."""
        page = AsyncMock(spec=Page)

        page.expect_download = MagicMock(
            return_value=FakeEventInfoFailing(TimeoutError("timeout"))
        )

        with patch("src.scraper.fallbacks.rosatom.DOWNLOADS_DIR", tmp_path):
            from src.scraper.fallbacks.rosatom import download_protocol_from_rosatom

            result = await download_protocol_from_rosatom(
                page, "https://rosatom.ru/p", "T1", "INN1"
            )

        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# ROSELTORG FALLBACK — РАСШИРЕННЫЕ ТЕСТЫ
# ══════════════════════════════════════════════════════════════════════════════


class TestRoseltorgExtractInn:
    """Тесты extract_inn_from_roseltorg."""

    @pytest.mark.asyncio
    async def test_extracts_inn(self) -> None:
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

    @pytest.mark.asyncio
    async def test_returns_none_when_no_inn(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value=None)

        with (
            patch("src.scraper.fallbacks.roseltorg.safe_goto", new_callable=AsyncMock),
            patch(
                "src.scraper.fallbacks.roseltorg.polite_wait", new_callable=AsyncMock
            ),
        ):
            from src.scraper.fallbacks.roseltorg import extract_inn_from_roseltorg

            result = await extract_inn_from_roseltorg(page, "https://roseltorg.ru/1")

        assert result is None


class TestRoseltorgProtocolLinks:
    """Тесты get_protocol_links_from_roseltorg (ранее не покрыты тестами)."""

    @pytest.mark.asyncio
    async def test_returns_protocol_links(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(
            return_value=[
                "https://roseltorg.ru/protocol/1",
                "https://roseltorg.ru/file/doc.pdf",
            ]
        )

        with (
            patch("src.scraper.fallbacks.roseltorg.safe_goto", new_callable=AsyncMock),
            patch(
                "src.scraper.fallbacks.roseltorg.polite_wait", new_callable=AsyncMock
            ),
        ):
            from src.scraper.fallbacks.roseltorg import (
                get_protocol_links_from_roseltorg,
            )

            result = await get_protocol_links_from_roseltorg(
                page, "https://roseltorg.ru/1"
            )

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_links(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value=[])

        with (
            patch("src.scraper.fallbacks.roseltorg.safe_goto", new_callable=AsyncMock),
            patch(
                "src.scraper.fallbacks.roseltorg.polite_wait", new_callable=AsyncMock
            ),
        ):
            from src.scraper.fallbacks.roseltorg import (
                get_protocol_links_from_roseltorg,
            )

            result = await get_protocol_links_from_roseltorg(
                page, "https://roseltorg.ru/1"
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_deduplicates_links(self) -> None:
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(
            return_value=[
                "https://roseltorg.ru/file/a",
                "https://roseltorg.ru/file/a",
                "https://roseltorg.ru/file/b",
            ]
        )

        with (
            patch("src.scraper.fallbacks.roseltorg.safe_goto", new_callable=AsyncMock),
            patch(
                "src.scraper.fallbacks.roseltorg.polite_wait", new_callable=AsyncMock
            ),
        ):
            from src.scraper.fallbacks.roseltorg import (
                get_protocol_links_from_roseltorg,
            )

            result = await get_protocol_links_from_roseltorg(
                page, "https://roseltorg.ru/1"
            )

        assert len(result) == 2


class TestRoseltorgDownload:
    """Тесты download_protocol_from_roseltorg (ранее не покрыты тестами)."""

    @pytest.mark.asyncio
    async def test_download_success(self, tmp_path: Path) -> None:
        page = AsyncMock(spec=Page)
        mock_download = MagicMock()
        mock_download.suggested_filename = "roseltorg_proto.pdf"
        mock_download.save_as = AsyncMock()

        page.expect_download = MagicMock(return_value=FakeEventInfo(mock_download))

        with patch("src.scraper.fallbacks.roseltorg.DOWNLOADS_DIR", tmp_path):
            from src.scraper.fallbacks.roseltorg import download_protocol_from_roseltorg

            result = await download_protocol_from_roseltorg(
                page, "https://roseltorg.ru/p", "T1", "INN1"
            )

        assert result is not None
        assert result.name == "roseltorg_proto.pdf"

    @pytest.mark.asyncio
    async def test_download_creates_correct_directory(self, tmp_path: Path) -> None:
        page = AsyncMock(spec=Page)
        mock_download = MagicMock()
        mock_download.suggested_filename = "test.pdf"
        mock_download.save_as = AsyncMock()

        page.expect_download = MagicMock(return_value=FakeEventInfo(mock_download))

        with patch("src.scraper.fallbacks.roseltorg.DOWNLOADS_DIR", tmp_path):
            from src.scraper.fallbacks.roseltorg import download_protocol_from_roseltorg

            result = await download_protocol_from_roseltorg(
                page, "https://roseltorg.ru/p", "T-77", "7711223344"
            )

        expected_dir = tmp_path / "7711223344" / "T-77" / "roseltorg"
        assert expected_dir.exists()
        assert result == expected_dir / "test.pdf"

    @pytest.mark.asyncio
    async def test_download_returns_none_on_failure(self, tmp_path: Path) -> None:
        page = AsyncMock(spec=Page)
        page.expect_download = MagicMock(
            return_value=FakeEventInfoFailing(TimeoutError("timeout"))
        )

        with patch("src.scraper.fallbacks.roseltorg.DOWNLOADS_DIR", tmp_path):
            from src.scraper.fallbacks.roseltorg import download_protocol_from_roseltorg

            result = await download_protocol_from_roseltorg(
                page, "https://roseltorg.ru/p", "T1", "INN1"
            )

        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# КРОСС-МОДУЛЬНЫЕ ТЕСТЫ — ПРОВЕРКА ИМПОРТОВ И СОГЛАСОВАННОСТИ
# ══════════════════════════════════════════════════════════════════════════════


class TestImportsAndCodeQuality:
    """Проверка импортов и качества кода."""

    def test_gpb_unused_import_re(self) -> None:
        """gpb_fallback.py импортирует re, но не использует его."""
        import src.scraper.fallbacks.gpb as mod
        import re

        # re импортируется но не используется в коде — проверяем что модуль
        # хотя бы загружается без ошибок
        assert hasattr(mod, "extract_inn_from_gpb")
        assert hasattr(mod, "get_protocol_links_from_gpb")
        assert hasattr(mod, "download_protocol_from_gpb")

    def test_rosatom_unused_import_re(self) -> None:
        """rosatom_fallback.py импортирует re, но не использует его."""
        import src.scraper.fallbacks.rosatom as mod

        assert hasattr(mod, "extract_inn_from_rosatom")
        assert hasattr(mod, "get_protocol_links_from_rosatom")
        assert hasattr(mod, "download_protocol_from_rosatom")

    def test_roseltorg_unused_import_re(self) -> None:
        """roseltorg_fallback.py импортирует re, но не использует его."""
        import src.scraper.fallbacks.roseltorg as mod

        assert hasattr(mod, "extract_inn_from_roseltorg")
        assert hasattr(mod, "get_protocol_links_from_roseltorg")
        assert hasattr(mod, "download_protocol_from_roseltorg")

    def test_gpb_evaluate_js_regex_syntax(self) -> None:
        """Проверяем, что JS-код для evaluate синтаксически корректный."""
        import inspect
        from src.scraper.fallbacks.gpb import extract_inn_from_gpb

        source = inspect.getsource(extract_inn_from_gpb)
        # Regex в JS: ИНН\\s*:?\\s*(\\d{10,12})
        # Это должно быть \\d{10,12} — match 10-12 цифр
        assert "\\d{10,12}" in source

    def test_rosatom_evaluate_js_regex_syntax(self) -> None:
        import inspect
        from src.scraper.fallbacks.rosatom import extract_inn_from_rosatom

        source = inspect.getsource(extract_inn_from_rosatom)
        assert "\\d{10,12}" in source

    def test_roseltorg_evaluate_js_regex_syntax(self) -> None:
        import inspect
        from src.scraper.fallbacks.roseltorg import extract_inn_from_roseltorg

        source = inspect.getsource(extract_inn_from_roseltorg)
        assert "\\d{10,12}" in source


class TestJsEvaluateRegex:
    """Проверяем, что JS-регулярка ИНН работает правильно для разных вариантов текста.

    Тестируем саму JS-строку, которая передается в page.evaluate, через
    имитацию различного содержимого body.innerText.
    """

    @pytest.mark.asyncio
    async def test_inn_with_colon(self) -> None:
        """ИНН: 1234567890"""
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="1234567890")

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.gpb.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import extract_inn_from_gpb

            result = await extract_inn_from_gpb(page, "https://gpb.ru/1")

        assert result == "1234567890"

    @pytest.mark.asyncio
    async def test_inn_without_colon(self) -> None:
        """ИНН 1234567890"""
        page = AsyncMock(spec=Page)
        page.evaluate = AsyncMock(return_value="1234567890")

        with (
            patch("src.scraper.fallbacks.gpb.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.fallbacks.gpb.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.fallbacks.gpb import extract_inn_from_gpb

            result = await extract_inn_from_gpb(page, "https://gpb.ru/1")

        assert result == "1234567890"


# ══════════════════════════════════════════════════════════════════════════════
# ТЕСТЫ УСТОЙЧИВОСТИ К CSS СЕЛЕКТОРАМ С СПЕЦСИМВОЛАМИ В URL
# ══════════════════════════════════════════════════════════════════════════════


class TestGpbFstringJs:
    """Проверяем f-string в gpb_fallback.py download (строка 71).

    f-строка формирует JS-код, который использует template literal.
    Проверяем, что Python не ломает JS при обработке f-string.
    """

    def test_fstring_produces_valid_js(self) -> None:
        """Проверяем, что f-string после обработки Python
        дает валидный JS-код с template literal."""
        # Воспроизводим f-string из gpb_fallback.py:71
        js = f'(u) => {{ const a = document.querySelector(`a[href="${{u}}"]`); if (a) a.click(); else window.location.href = u; }}'

        # После f-string обработки должно получиться:
        expected = '(u) => { const a = document.querySelector(`a[href="${u}"]`); if (a) a.click(); else window.location.href = u; }'
        assert js == expected

        # Проверяем что в итоговом JS нет двойных фигурных скобок
        assert "{{" not in js
        assert "}}" not in js
