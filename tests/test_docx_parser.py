"""Тесты для src/parser/docx_parser.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.parser.docx_parser import _analyze_tables, extract_participants_from_docx


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_mock_doc(paragraphs: list[str], tables: list[list[list[str]]] | None = None):
    """Создаёт мок Document с параграфами и таблицами.

    tables: list of tables, each table is list of rows, each row is list of cell texts.
    """
    doc = MagicMock()

    # Paragraphs
    mock_paras = []
    for text in paragraphs:
        p = MagicMock()
        p.text = text
        mock_paras.append(p)
    doc.paragraphs = mock_paras

    # Tables
    mock_tables = []
    if tables:
        for table_data in tables:
            table = MagicMock()
            mock_rows = []
            for row_data in table_data:
                row = MagicMock()
                mock_cells = []
                for cell_text in row_data:
                    cell = MagicMock()
                    cell.text = cell_text
                    mock_cells.append(cell)
                row.cells = mock_cells
                mock_rows.append(row)
            table.rows = mock_rows
            mock_tables.append(table)
    doc.tables = mock_tables

    return doc


# ═══════════════════════════════════════════════════════════════════════════════
# _analyze_tables
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalyzeTables:
    def test_table_with_participant_header(self):
        """Таблица с заголовком 'Участник' — считает строки данных."""
        doc = _make_mock_doc(
            [],
            tables=[
                [
                    ["№", "Участник", "ИНН"],
                    ["1", "ООО Альфа", "1111111111"],
                    ["2", "ООО Бета", "2222222222"],
                ]
            ],
        )
        result = _analyze_tables(doc)
        assert result is not None
        assert result.count == 2
        assert result.method == "docx_table_participant_rows"

    def test_table_with_naimenovanie_header(self):
        """Заголовок 'Наименование' тоже распознаётся."""
        doc = _make_mock_doc(
            [],
            tables=[
                [
                    ["Наименование", "Цена"],
                    ["ООО Гамма", "100"],
                ]
            ],
        )
        result = _analyze_tables(doc)
        assert result is not None
        assert result.count == 1

    def test_table_with_supplier_header(self):
        """Заголовок 'Поставщик' распознаётся."""
        doc = _make_mock_doc(
            [],
            tables=[
                [
                    ["Поставщик", "Сумма"],
                    ["ИП Иванов", "500"],
                    ["ООО Строй", "600"],
                    ["АО Монтаж", "700"],
                ]
            ],
        )
        result = _analyze_tables(doc)
        assert result is not None
        assert result.count == 3

    def test_itogo_row_excluded(self):
        """Строка 'Итого' не считается как участник."""
        doc = _make_mock_doc(
            [],
            tables=[
                [
                    ["Участник", "Цена"],
                    ["ООО Альфа", "100"],
                    ["Итого", "100"],
                ]
            ],
        )
        result = _analyze_tables(doc)
        assert result is not None
        assert result.count == 1  # "Итого" excluded

    def test_empty_rows_excluded(self):
        """Пустые строки не считаются."""
        doc = _make_mock_doc(
            [],
            tables=[
                [
                    ["Участник", "Цена"],
                    ["ООО Альфа", "100"],
                    ["  ", "  "],
                ]
            ],
        )
        result = _analyze_tables(doc)
        assert result is not None
        assert result.count == 1

    def test_no_matching_header(self):
        """Таблица без подходящего заголовка — возвращает None."""
        doc = _make_mock_doc(
            [],
            tables=[
                [
                    ["Дата", "Сумма"],
                    ["01.01", "100"],
                ]
            ],
        )
        result = _analyze_tables(doc)
        assert result is None

    def test_empty_table(self):
        """Таблица без строк — пропускается."""
        doc = _make_mock_doc([], tables=[])
        result = _analyze_tables(doc)
        assert result is None

    def test_table_no_rows(self):
        """Таблица с пустым rows — пропускается."""
        doc = MagicMock()
        table = MagicMock()
        table.rows = []
        doc.tables = [table]
        result = _analyze_tables(doc)
        assert result is None

    def test_header_case_insensitive(self):
        """Поиск заголовка нечувствителен к регистру."""
        doc = _make_mock_doc(
            [],
            tables=[
                [
                    ["УЧАСТНИК", "ЦЕНА"],
                    ["ООО Тест", "100"],
                ]
            ],
        )
        result = _analyze_tables(doc)
        assert result is not None
        assert result.count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# extract_participants_from_docx
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractParticipantsFromDocx:
    def test_text_pattern_found_in_paragraphs(self, tmp_path: Path):
        """Паттерн найден в тексте параграфов."""
        doc = _make_mock_doc(["Подано 5 заявок на участие"])

        with patch("docx.Document", return_value=doc):
            result = extract_participants_from_docx(tmp_path / "test.docx")

        assert result.count == 5
        assert result.method.startswith("docx_")

    def test_text_pattern_in_table_cells(self, tmp_path: Path):
        """Паттерн найден в тексте ячеек таблицы."""
        doc = _make_mock_doc(
            [],
            tables=[
                [
                    ["Подано 3 заявки на участие"],
                ]
            ],
        )

        with patch("docx.Document", return_value=doc):
            result = extract_participants_from_docx(tmp_path / "test.docx")

        assert result.count == 3

    def test_table_analysis_fallback(self, tmp_path: Path):
        """Если regex не сработал — фолбэк на анализ таблиц."""
        doc = _make_mock_doc(
            ["Какой-то текст без паттерна"],
            tables=[
                [
                    ["Участник", "Цена"],
                    ["ООО Альфа", "100"],
                    ["ООО Бета", "200"],
                ]
            ],
        )

        with patch("docx.Document", return_value=doc):
            result = extract_participants_from_docx(tmp_path / "test.docx")

        assert result.count == 2
        assert result.method == "docx_table_participant_rows"

    def test_empty_document(self, tmp_path: Path):
        """Пустой документ — docx_empty."""
        doc = _make_mock_doc([])

        with patch("docx.Document", return_value=doc):
            result = extract_participants_from_docx(tmp_path / "test.docx")

        assert result.count is None
        assert result.method == "docx_empty"

    def test_no_pattern_found(self, tmp_path: Path):
        """Текст есть, но паттерн не найден и таблиц нет — docx_no_pattern."""
        doc = _make_mock_doc(["Просто текст без информации об участниках"])

        with patch("docx.Document", return_value=doc):
            result = extract_participants_from_docx(tmp_path / "test.docx")

        assert result.count is None
        assert result.method == "docx_no_pattern"

    def test_document_open_error(self, tmp_path: Path):
        """Ошибка при открытии файла — docx_open_error."""
        with patch(
            "docx.Document",
            side_effect=Exception("corrupt file"),
        ):
            result = extract_participants_from_docx(tmp_path / "bad.docx")

        assert result.count is None
        assert result.method == "docx_open_error"

    def test_import_error(self, tmp_path: Path):
        """python-docx не установлен — docx_import_error."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "docx":
                raise ImportError("No module named 'docx'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = extract_participants_from_docx(tmp_path / "test.docx")

        assert result.count is None
        assert result.method == "docx_import_error"
