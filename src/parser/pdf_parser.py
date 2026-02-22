"""Парсинг текстовых .pdf протоколов для извлечения числа участников.

Поддерживает только текстовые PDF (с копируемым текстом).
PDF-сканы (изображения) пропускаются — по ТЗ OCR пока не требуется.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.parser.participant_patterns import (
    ParticipantResult,
    extract_participants_from_text,
)


def is_scan_pdf(file_path: Path) -> bool:
    """Проверяет, является ли PDF сканом (без текстового слоя).

    Критерий: если pdfplumber извлекает менее 50 символов текста
    со всех страниц — считаем скан.
    """
    try:
        import pdfplumber  # type: ignore[import-untyped]
    except ImportError:
        logger.error("pdfplumber не установлен")
        return True  # На всякий случай считаем сканом

    try:
        with pdfplumber.open(str(file_path)) as pdf:
            total_chars = 0
            for page in pdf.pages:
                text = page.extract_text() or ""
                total_chars += len(text.strip())
                if total_chars >= 50:
                    return False
            return total_chars < 50
    except Exception as exc:
        logger.error("Ошибка при проверке PDF {}: {}", file_path.name, exc)
        return True


def extract_participants_from_pdf(file_path: Path) -> ParticipantResult:
    """Извлекает количество участников из текстового .pdf файла протокола.

    PDF-сканы (без текстового слоя) пропускаются — возвращается результат
    с parse_status-совместимым method="pdf_scan_skip".

    Args:
        file_path: Путь к .pdf файлу.

    Returns:
        ParticipantResult с количеством и методом извлечения.
    """
    try:
        import pdfplumber  # type: ignore[import-untyped]
    except ImportError:
        logger.error("pdfplumber не установлен, невозможно парсить .pdf")
        return ParticipantResult(
            count=None, method="pdf_import_error", confidence="low"
        )

    # Проверяем, не скан ли это
    if is_scan_pdf(file_path):
        logger.info("PDF {} — скан (без текста), пропускаем", file_path.name)
        return ParticipantResult(count=None, method="pdf_scan_skip", confidence="low")

    try:
        text_parts: list[str] = []
        table_text_parts: list[str] = []

        with pdfplumber.open(str(file_path)) as pdf:
            logger.debug("PDF {}: {} страниц", file_path.name, len(pdf.pages))

            for page_num, page in enumerate(pdf.pages, 1):
                # Извлекаем текст страницы
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text)

                # Извлекаем таблицы
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if row:
                            cells = [str(cell).strip() for cell in row if cell]
                            if cells:
                                table_text_parts.append(" | ".join(cells))

        # Объединяем весь текст
        full_text = "\n".join(text_parts)
        if table_text_parts:
            full_text += "\n" + "\n".join(table_text_parts)

        if not full_text.strip():
            logger.warning("PDF {} не содержит извлекаемого текста", file_path.name)
            return ParticipantResult(count=None, method="pdf_empty", confidence="low")

        logger.debug(
            "PDF {}: {} символов текста ({} страниц)",
            file_path.name,
            len(full_text),
            len(text_parts),
        )

        # Применяем общие regex-паттерны
        result = extract_participants_from_text(full_text)
        if result.count is not None:
            result.method = f"pdf_{result.method}"
            return result

        logger.info("PDF {}: не удалось определить число участников", file_path.name)
        return ParticipantResult(count=None, method="pdf_no_pattern", confidence="low")

    except Exception as exc:
        logger.error("Ошибка при парсинге PDF {}: {}", file_path.name, exc)
        return ParticipantResult(count=None, method="pdf_parse_error", confidence="low")
