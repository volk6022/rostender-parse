"""Tests for parser/participant_patterns.py."""

from __future__ import annotations

import pytest

from src.parser.participant_patterns import (
    ParticipantParsingResult,
    ParticipantResult,
    extract_participants_from_text,
)


class TestExtractParticipantsFromText:
    """Tests for extract_participants_from_text function."""

    def test_direct_count_applications(self, sample_protocol_texts: dict) -> None:
        """Тест паттерна 'Количество поданных заявок: N'."""
        result = extract_participants_from_text(sample_protocol_texts["direct_count"])

        assert result.count == 5
        assert result.method == "direct_count_applications"
        assert result.confidence == "high"

    def test_submitted_applications(self, sample_protocol_texts: dict) -> None:
        """Тест паттерна 'Подано N заявки'."""
        result = extract_participants_from_text(sample_protocol_texts["submitted"])

        assert result.count == 3
        assert result.method == "submitted_N_applications"
        assert result.confidence == "high"

    def test_direct_count_participants(self, sample_protocol_texts: dict) -> None:
        """Тест паттерна 'Количество участников: N'."""
        result = extract_participants_from_text(
            sample_protocol_texts["participants_count"]
        )

        assert result.count == 2
        assert result.method == "direct_count_participants"
        assert result.confidence == "high"

    def test_admitted_participants(self, sample_protocol_texts: dict) -> None:
        """Тест паттерна 'Допущено N участника'."""
        result = extract_participants_from_text(sample_protocol_texts["admitted"])

        assert result.count == 4
        assert result.method == "admitted_N_participants"
        assert result.confidence == "high"

    def test_single_participant(self, sample_protocol_texts: dict) -> None:
        """Тест паттерна 'единственная заявка'."""
        result = extract_participants_from_text(sample_protocol_texts["single"])

        assert result.count == 1
        assert result.method == "single_participant"
        assert result.confidence == "high"

    def test_zero_applications(self, sample_protocol_texts: dict) -> None:
        """Тест паттерна 'заявок не поступило'."""
        result = extract_participants_from_text(sample_protocol_texts["zero"])

        assert result.count == 0
        assert result.method == "zero_applications"
        assert result.confidence == "high"

    def test_numbered_applications(self, sample_protocol_texts: dict) -> None:
        """Тест нумерованных заявок."""
        result = extract_participants_from_text(sample_protocol_texts["numbered_apps"])

        assert result.count == 3
        assert result.method == "numbered_applications"
        assert result.confidence == "medium"

    def test_numbered_org_rows(self, sample_protocol_texts: dict) -> None:
        """Тест нумерованных строк организаций."""
        result = extract_participants_from_text(sample_protocol_texts["numbered_orgs"])

        assert result.count == 3
        assert result.method == "numbered_org_rows"
        assert result.confidence == "medium"

    def test_inn_count(self, sample_protocol_texts: dict) -> None:
        """Тест подсчёта уникальных ИНН."""
        text = """
        ИНН: 1234567890
        ИНН: 1234567891
        ИНН: 1234567892
        ИНН: 1234567893
        """
        result = extract_participants_from_text(text)

        assert result.count == 3  # 4 - 1 (заказчик)
        assert result.method == "unique_inn_count"
        assert result.confidence == "low"

    def test_void_tender(self, sample_protocol_texts: dict) -> None:
        """Тест паттерна 'тендер признан несостоявшимся'."""
        result = extract_participants_from_text(sample_protocol_texts["void_tender"])

        assert result.count == 1
        assert result.method == "void_tender"
        assert result.confidence == "low"

    def test_empty_text(self) -> None:
        """Пустой текст."""
        result = extract_participants_from_text("")

        assert result.count is None
        assert result.method == "empty_text"
        assert result.confidence == "low"

    def test_whitespace_only(self) -> None:
        """Только пробелы и переносы строк."""
        result = extract_participants_from_text("   \n\n   \t  ")

        assert result.count is None
        assert result.method == "empty_text"
        assert result.confidence == "low"

    def test_no_pattern_matched(self) -> None:
        """Текст без распознаваемых паттернов."""
        text = """
        Протокол
        Дата: 01.01.2026
        Место проведения: г. Москва
        """
        result = extract_participants_from_text(text)

        assert result.count is None
        assert result.method == "no_pattern_matched"
        assert result.confidence == "low"

    def test_priority_order_direct_first(self) -> None:
        """Приоритет: прямые указания важнее косвенных."""
        text = """
        Количество участников: 10
        Заявка №5 ООО "Ромашка"
        Заявка №3 АО "Василёк"
        """
        result = extract_participants_from_text(text)

        assert result.count == 10
        assert result.method == "direct_count_participants"

    def test_russian_case_insensitive(self) -> None:
        """Регистронезависимость для русских слов."""
        text = "КОЛИЧЕСТВО УЧАСТНИКОВ: 7"
        result = extract_participants_from_text(text)

        assert result.count == 7
        assert result.method == "direct_count_participants"


class TestParticipantResult:
    """Tests for ParticipantResult / ParticipantParsingResult dataclass."""

    def test_dataclass_fields(self) -> None:
        """Проверка полей дата-класса."""
        result = ParticipantParsingResult(
            count=5,
            numbers=[1, 2, 3, 4, 5],
            method="test_method",
            confidence="high",
        )

        assert result.count == 5
        assert result.method == "test_method"
        assert result.confidence == "high"
        assert result.numbers == [1, 2, 3, 4, 5]

    def test_none_count_allowed(self) -> None:
        """None значение для count допустимо."""
        result = ParticipantParsingResult(
            count=None,
            numbers=[],
            method="no_data",
            confidence="low",
        )

        assert result.count is None

    def test_participant_result_alias(self) -> None:
        """ParticipantResult — алиас для ParticipantParsingResult."""
        assert ParticipantResult is ParticipantParsingResult
