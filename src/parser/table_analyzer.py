"""Общая логика анализа таблиц протоколов (DOCX и PDF).

Предоставляет:
- Абстрактный интерфейс ProtocolParser
- Общие утилиты для работы с таблицами
- MultiProtocolAnalysis для агрегации заявок из нескольких протоколов
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from src.parser.participant_patterns import (
    ALL_PARTICIPANT_HEADERS,
    ParticipantParsingResult,
    TABLE_HEADERS,
)


# ── Абстрактный интерфейс парсера ─────────────────────────────────────────────


class ProtocolParser(ABC):
    """Абстрактный базовый класс для парсеров протоколов.

    Определяет единый интерфейс, который должны реализовывать
    DocxProtocolParser и PdfProtocolParser.
    """

    @abstractmethod
    def parse(self, file_path: Path) -> ParticipantParsingResult:
        """Парсит файл протокола и возвращает результат.

        Args:
            file_path: Путь к файлу протокола.

        Returns:
            ParticipantParsingResult с количеством участников и номерами заявок.
        """
        ...

    @abstractmethod
    def extract_application_numbers(self, content: object) -> list[int]:
        """Извлекает номера заявок из содержимого (таблица, страница и т.п.).

        Args:
            content: Содержимое для анализа (зависит от формата).

        Returns:
            Список уникальных номеров заявок.
        """
        ...


class DocxProtocolParser(ProtocolParser):
    """Парсер протоколов в формате .docx."""

    def parse(self, file_path: Path) -> ParticipantParsingResult:
        from src.parser.docx_parser import extract_participants_from_docx

        return extract_participants_from_docx(file_path)

    def extract_application_numbers(self, content: object) -> list[int]:
        from src.parser.docx_parser import extract_application_numbers_from_table

        return extract_application_numbers_from_table(content)


class PdfProtocolParser(ProtocolParser):
    """Парсер протоколов в формате .pdf."""

    def parse(self, file_path: Path) -> ParticipantParsingResult:
        from src.parser.pdf_parser import extract_participants_from_pdf

        return extract_participants_from_pdf(file_path)

    def extract_application_numbers(self, content: object) -> list[int]:
        from src.parser.pdf_parser import extract_application_numbers_from_pdf_table

        return extract_application_numbers_from_pdf_table(content)  # type: ignore[arg-type]


# ── Агрегация заявок из нескольких протоколов ─────────────────────────────────


@dataclass
class ProtocolData:
    """Данные одного протокола в рамках тендера."""

    protocol_index: int  # Порядковый номер протокола (1, 2, 3...)
    file_path: str | None  # Путь к файлу
    parse_source: str | None  # docx | pdf_text | html | ...
    application_numbers: list[int]  # Номера заявок из этого протокола
    raw_count: int | None  # Сырое количество из протокола
    parse_method: str  # Метод извлечения
    confidence: str  # high | medium | low


@dataclass
class MultiProtocolAnalysis:
    """Агрегирует данные из нескольких протоколов одного тендера.

    Выполняет дедупликацию заявок по номерам между всеми протоколами.
    """

    tender_id: str
    protocols: list[ProtocolData] = field(default_factory=list)
    all_applications: set[int] = field(default_factory=set)

    def add_protocol(self, protocol: ProtocolData) -> None:
        """Добавляет данные протокола и обновляет общий набор заявок."""
        self.protocols.append(protocol)
        if protocol.application_numbers:
            self.all_applications.update(protocol.application_numbers)

    def get_final_count(self) -> int | None:
        """Возвращает итоговое количество уникальных заявок.

        Если есть номера заявок — возвращает количество уникальных.
        Иначе — максимальное raw_count среди протоколов.
        """
        if self.all_applications:
            return len(self.all_applications)

        # Нет номеров — берём максимальный raw_count
        counts = [p.raw_count for p in self.protocols if p.raw_count is not None]
        return max(counts) if counts else None

    def get_best_confidence(self) -> str:
        """Возвращает наивысший уровень уверенности среди протоколов."""
        priority = {"high": 0, "medium": 1, "low": 2}
        best = min(
            (p.confidence for p in self.protocols),
            key=lambda c: priority.get(c, 99),
            default="low",
        )
        return best

    def has_deduplication(self) -> bool:
        """True если среди протоколов были дубликаты заявок."""
        if not self.all_applications:
            return False
        total_raw = sum(len(p.application_numbers) for p in self.protocols)
        return total_raw > len(self.all_applications)

    def summary_notes(self) -> str:
        """Генерирует строку с описанием результата для поля notes в БД."""
        parts = [
            f"протоколов: {len(self.protocols)}",
            f"уникальных заявок: {self.get_final_count()}",
        ]
        if self.has_deduplication():
            parts.append("дедупликация применена")
        return ", ".join(parts)


# ── Общие утилиты ─────────────────────────────────────────────────────────────


def is_participant_table_by_headers(header_cells: list[str]) -> bool:
    """Проверяет, является ли строка заголовков строкой таблицы с участниками.

    Args:
        header_cells: Список текстов ячеек заголовочной строки (в нижнем регистре).

    Returns:
        True если хотя бы одна ячейка соответствует заголовкам участников.
    """
    return any(
        any(ph in cell_text for ph in ALL_PARTICIPANT_HEADERS)
        for cell_text in header_cells
    )


def is_participant_table_by_title(title: str) -> bool:
    """Проверяет, является ли заголовок названием таблицы с участниками.

    Args:
        title: Текст заголовка (название таблицы, параграф перед ней).

    Returns:
        True если заголовок соответствует таблице с участниками/заявками.
    """
    title_lower = title.lower()
    return any(ph in title_lower for ph in ALL_PARTICIPANT_HEADERS)


def deduplicate_application_numbers(
    numbers_lists: list[list[int]],
) -> tuple[set[int], bool]:
    """Дедуплицирует номера заявок из нескольких источников.

    Args:
        numbers_lists: Список списков номеров заявок (по одному на таблицу/протокол).

    Returns:
        Кортеж (уникальные_номера, была_ли_дедупликация).
    """
    unique: set[int] = set()
    total = 0
    for numbers in numbers_lists:
        total += len(numbers)
        unique.update(numbers)
    return unique, total > len(unique)
