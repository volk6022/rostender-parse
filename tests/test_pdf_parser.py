"""Тесты для src/parser/pdf_parser.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.parser.pdf_parser import extract_participants_from_pdf, is_scan_pdf


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_mock_pdf(pages_text: list[str], tables: list[list[list[str]]] | None = None):
    """Создаёт мок pdfplumber PDF с текстом и таблицами."""
    pdf = MagicMock()
    mock_pages = []
    for i, text in enumerate(pages_text):
        page = MagicMock()
        page.extract_text.return_value = text
        # Tables per page — only first page gets tables if provided
        if tables and i == 0:
            page.extract_tables.return_value = tables
        else:
            page.extract_tables.return_value = []
        mock_pages.append(page)
    pdf.pages = mock_pages
    pdf.__enter__ = MagicMock(return_value=pdf)
    pdf.__exit__ = MagicMock(return_value=False)
    return pdf


# ═══════════════════════════════════════════════════════════════════════════════
# is_scan_pdf
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsScanPdf:
    def test_text_pdf_not_scan(self, tmp_path: Path):
        """PDF с достаточным текстом — не скан."""
        pdf = _make_mock_pdf(["A" * 100])

        with patch("pdfplumber.open", return_value=pdf):
            result = is_scan_pdf(tmp_path / "text.pdf")

        assert result is False

    def test_empty_pdf_is_scan(self, tmp_path: Path):
        """PDF без текста — скан."""
        pdf = _make_mock_pdf([""])

        with patch("pdfplumber.open", return_value=pdf):
            result = is_scan_pdf(tmp_path / "scan.pdf")

        assert result is True

    def test_short_text_is_scan(self, tmp_path: Path):
        """PDF с < 50 символами — скан."""
        pdf = _make_mock_pdf(["Short text"])  # 10 chars

        with patch("pdfplumber.open", return_value=pdf):
            result = is_scan_pdf(tmp_path / "short.pdf")

        assert result is True

    def test_exactly_50_chars_not_scan(self, tmp_path: Path):
        """PDF ровно с 50 символами — не скан (>= 50)."""
        pdf = _make_mock_pdf(["A" * 50])

        with patch("pdfplumber.open", return_value=pdf):
            result = is_scan_pdf(tmp_path / "border.pdf")

        assert result is False

    def test_multipage_cumulative(self, tmp_path: Path):
        """Многостраничный PDF — суммируется текст со всех страниц."""
        pdf = _make_mock_pdf(["A" * 30, "B" * 30])  # total 60 chars

        with patch("pdfplumber.open", return_value=pdf):
            result = is_scan_pdf(tmp_path / "multi.pdf")

        assert result is False

    def test_none_text_treated_as_empty(self, tmp_path: Path):
        """page.extract_text() возвращает None — считается как пустой."""
        pdf = _make_mock_pdf([])
        page = MagicMock()
        page.extract_text.return_value = None
        pdf.pages = [page]

        with patch("pdfplumber.open", return_value=pdf):
            result = is_scan_pdf(tmp_path / "none.pdf")

        assert result is True

    def test_exception_returns_true(self, tmp_path: Path):
        """Ошибка при открытии — считаем сканом (безопасный fallback)."""
        with patch("pdfplumber.open", side_effect=Exception("corrupt")):
            result = is_scan_pdf(tmp_path / "bad.pdf")

        assert result is True

    def test_import_error_returns_true(self, tmp_path: Path):
        """pdfplumber не установлен — считаем сканом."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pdfplumber":
                raise ImportError("No module named 'pdfplumber'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = is_scan_pdf(tmp_path / "noimport.pdf")

        assert result is True


# ═══════════════════════════════════════════════════════════════════════════════
# extract_participants_from_pdf
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractParticipantsFromPdf:
    def test_text_pdf_with_pattern(self, tmp_path: Path):
        """PDF с распознаваемым текстовым паттерном."""
        pdf = _make_mock_pdf(["Подано 5 заявок на участие"])

        with (
            patch("pdfplumber.open", return_value=pdf),
            patch("src.parser.pdf_parser.is_scan_pdf", return_value=False),
        ):
            result = extract_participants_from_pdf(tmp_path / "test.pdf")

        assert result.count == 5
        assert result.method.startswith("pdf_")

    def test_scan_pdf_skipped(self, tmp_path: Path):
        """PDF-скан — возвращает pdf_scan_skip."""
        with patch("src.parser.pdf_parser.is_scan_pdf", return_value=True):
            result = extract_participants_from_pdf(tmp_path / "scan.pdf")

        assert result.count is None
        assert result.method == "pdf_scan_skip"

    def test_no_pattern_found(self, tmp_path: Path):
        """Текст есть, но паттерн не найден."""
        pdf = _make_mock_pdf(["Просто текст без информации"])

        with (
            patch("pdfplumber.open", return_value=pdf),
            patch("src.parser.pdf_parser.is_scan_pdf", return_value=False),
        ):
            result = extract_participants_from_pdf(tmp_path / "nopat.pdf")

        assert result.count is None
        assert result.method == "pdf_no_pattern"

    def test_empty_text_pdf(self, tmp_path: Path):
        """PDF с пустым текстом (не скан по is_scan_pdf, но нет контента)."""
        pdf = _make_mock_pdf([""])

        with (
            patch("pdfplumber.open", return_value=pdf),
            patch("src.parser.pdf_parser.is_scan_pdf", return_value=False),
        ):
            result = extract_participants_from_pdf(tmp_path / "empty.pdf")

        assert result.count is None
        assert result.method == "pdf_empty"

    def test_table_text_included(self, tmp_path: Path):
        """Текст из таблиц тоже анализируется."""
        pdf = _make_mock_pdf(
            ["Какой-то текст"],
            tables=[[["Подано 3 заявки", "на участие"]]],
        )

        with (
            patch("pdfplumber.open", return_value=pdf),
            patch("src.parser.pdf_parser.is_scan_pdf", return_value=False),
        ):
            result = extract_participants_from_pdf(tmp_path / "tables.pdf")

        assert result.count == 3

    def test_multipage_text(self, tmp_path: Path):
        """Текст собирается со всех страниц."""
        pdf = _make_mock_pdf(
            [
                "Страница 1: текст без паттерна",
                "Подано 7 заявок на участие",
            ]
        )

        with (
            patch("pdfplumber.open", return_value=pdf),
            patch("src.parser.pdf_parser.is_scan_pdf", return_value=False),
        ):
            result = extract_participants_from_pdf(tmp_path / "multi.pdf")

        assert result.count == 7

    def test_parse_exception(self, tmp_path: Path):
        """Исключение при парсинге — pdf_parse_error."""
        with (
            patch("pdfplumber.open", side_effect=Exception("corrupt PDF")),
            patch("src.parser.pdf_parser.is_scan_pdf", return_value=False),
        ):
            result = extract_participants_from_pdf(tmp_path / "bad.pdf")

        assert result.count is None
        assert result.method == "pdf_parse_error"

    def test_import_error(self, tmp_path: Path):
        """pdfplumber не установлен — pdf_import_error."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pdfplumber":
                raise ImportError("No module named 'pdfplumber'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = extract_participants_from_pdf(tmp_path / "noimport.pdf")

        assert result.count is None
        assert result.method == "pdf_import_error"
