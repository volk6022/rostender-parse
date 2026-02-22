"""Парсинг .docx протоколов для извлечения числа участников.

Стратегии (в порядке приоритета):
1. Поиск в тексте параграфов через regex-паттерны
2. Анализ таблиц — поиск строк с заголовками «Участник»/«Наименование»
3. Подсчёт нумерованных строк в таблицах
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.parser.participant_patterns import (
    ParticipantResult,
    extract_participants_from_text,
)


def extract_participants_from_docx(file_path: Path) -> ParticipantResult:
    """Извлекает количество участников из .docx файла протокола.

    Args:
        file_path: Путь к .docx файлу.

    Returns:
        ParticipantResult с количеством и методом извлечения.
    """
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError:
        logger.error("python-docx не установлен, невозможно парсить .docx")
        return ParticipantResult(
            count=None, method="docx_import_error", confidence="low"
        )

    try:
        doc = Document(str(file_path))
    except Exception as exc:
        logger.error("Ошибка при открытии .docx файла {}: {}", file_path, exc)
        return ParticipantResult(count=None, method="docx_open_error", confidence="low")

    # ── Стратегия 1: Собираем весь текст параграфов + текст таблиц ───────
    all_text_parts: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            all_text_parts.append(text)

    # Текст из таблиц тоже добавляем (часто участники перечислены в таблицах)
    for table in doc.tables:
        for row in table.rows:
            row_texts = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text:
                    row_texts.append(cell_text)
            if row_texts:
                all_text_parts.append(" | ".join(row_texts))

    full_text = "\n".join(all_text_parts)

    if not full_text.strip():
        logger.warning("Файл {} не содержит текста", file_path.name)
        return ParticipantResult(count=None, method="docx_empty", confidence="low")

    logger.debug(
        "DOCX {}: {} параграфов, {} таблиц, {} символов текста",
        file_path.name,
        len(doc.paragraphs),
        len(doc.tables),
        len(full_text),
    )

    # ── Стратегия 1: regex-паттерны по тексту ────────────────────────────
    result = extract_participants_from_text(full_text)
    if result.count is not None:
        result.method = f"docx_{result.method}"
        return result

    # ── Стратегия 2: Анализ таблиц — подсчёт строк данных ────────────────
    table_result = _analyze_tables(doc)
    if table_result is not None:
        return table_result

    # Ничего не найдено
    logger.info("DOCX {}: не удалось определить число участников", file_path.name)
    return ParticipantResult(count=None, method="docx_no_pattern", confidence="low")


def _analyze_tables(doc) -> ParticipantResult | None:
    """Анализирует таблицы .docx документа для подсчёта участников.

    Ищет таблицы с заголовками, содержащими «Участник», «Наименование»,
    «Поставщик» и т.п. Считает количество строк данных (минус заголовок).
    """
    participant_headers = {
        "участник",
        "наименование участника",
        "наименование",
        "поставщик",
        "претендент",
        "заявитель",
        "организация",
        "наименование организации",
    }

    for table_idx, table in enumerate(doc.tables):
        if not table.rows:
            continue

        # Проверяем, есть ли заголовок таблицы с нужными словами
        header_row = table.rows[0]
        header_cells = [cell.text.strip().lower() for cell in header_row.cells]

        has_participant_header = any(
            any(ph in cell_text for ph in participant_headers)
            for cell_text in header_cells
        )

        if not has_participant_header:
            continue

        # Считаем непустые строки данных (кроме заголовка)
        data_rows = 0
        for row in table.rows[1:]:
            # Проверяем, что строка содержит хоть какие-то данные
            row_text = " ".join(cell.text.strip() for cell in row.cells)
            if row_text.strip() and not row_text.lower().startswith("итого"):
                data_rows += 1

        if data_rows > 0:
            logger.debug(
                "Таблица #{}: найден заголовок с участниками, строк данных: {}",
                table_idx,
                data_rows,
            )
            return ParticipantResult(
                count=data_rows,
                method="docx_table_participant_rows",
                confidence="medium",
            )

    return None
