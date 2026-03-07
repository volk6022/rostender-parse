"""Скрипт для анализа протоколов из теста в downloads-proccessed.md.

Читает markdown файл, для каждой записи ищет файл в директории downloads,
запускает парсинг и записывает результаты в JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from src.parser.participant_patterns import extract_participants_from_text


def load_test_data(markdown_path: Path) -> list[dict[str, str]]:
    """Читает downloads-proccessed.md и возвращает список записей."""
    records: list[dict[str, str]] = []

    with open(markdown_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Пропускаем заголовок
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        # Парсим строку таблицы: "| X | path/to/file|"
        match = re.match(r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|", line)
        if match:
            count_str = match.group(1)
            path_part = match.group(2).strip()
            records.append(
                {
                    "count": int(count_str) if count_str != "-" else 0,
                    "path_part": path_part,
                }
            )

    return records


def find_file_in_downloads(path_part: str, downloads_dir: Path) -> Path | None:
    """Ищет файл по частичному совпадению в директории downloads.

    Аргумент path_part начинается с корня директории и уникален на определённом префиксе.
    """
    downloads_dir = downloads_dir.resolve()

    # Ищем все до каталогов и файлов
    matches: list[Path] = []
    for match_path in downloads_dir.rglob("*"):
        if match_path.is_file():
            full_path = match_path.resolve()
            # Проверяем совпадение с начало строки
            if str(full_path).startswith(path_part) or str(full_path).startswith(
                path_part.rstrip("/")
            ):
                try:
                    if full_path.name.startswith(path_part.split("/")[-1]):
                        matches.append(full_path)
                except Exception:
                    continue

    if matches:
        # Возвратим первый подходящий
        return matches[0]

    # Попытка найти по имя файла (последний слэш)
    filename_only = path_part.split("/")[-1]
    if filename_only:
        for match_path in downloads_dir.rglob("*"):
            if match_path.is_file() and filename_only in match_path.name:
                return match_path.resolve()

    logger.warning(f"Файл не найден по паттерну: {path_part!r}")
    return None


def parse_file_test(file_path: Path) -> dict[str, Any]:
    """Запускает тестовый парсинг файла (только из текста)."""
    result: dict[str, Any] = {
        "file": file_path.name,
        "file_size": file_path.stat().st_size,
        "parse_success": False,
        "extracted_count": None,
        "extracted_numbers": [],
        "method": None,
        "confidence": None,
        "error": None,
    }

    try:
        # Пытаемся прочитать как текст
        text = file_path.read_text(encoding="utf-8", errors="replace")

        if len(text.strip()) > 50:
            parsed = extract_participants_from_text(text)
            result["extracted_count"] = parsed.count
            result["extracted_numbers"] = parsed.numbers
            result["method"] = parsed.method
            result["confidence"] = parsed.confidence

            if parsed.count is not None:
                result["parse_success"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


def generate_full_report(file_path: Path, parse_result: dict[str, Any]) -> Any:
    """Генерирует полные данные для файла."""
    return {
        "file_path": str(file_path),
        "file_name": file_path.name,
        "file_size": parse_result["file_size"],
        "parse_result": parse_result,
    }


def generate_brief_report(
    file_path: Path, parse_result: dict[str, Any]
) -> dict[str, Any]:
    """Генерирует краткий отчёт."""
    return {
        "file": file_path.name,
        "count_extracted": parse_result["extracted_count"],
        "method": parse_result["method"],
        "confidence": parse_result["confidence"],
        "parse_success": parse_result["parse_success"],
        "error": parse_result["error"],
    }


def main() -> None:
    """Главная функция анализа."""
    # Пути
    root_dir = Path(__file__).parent
    markdown_path = Path(__file__).parent / "downloads-proccessed.md"
    json_path = Path(__file__).parent / "analysis_test_results.json"

    # Загружаем тестовые данные
    logger.info("Чтение файла с тестами: {}", markdown_path)
    test_records = load_test_data(markdown_path)
    logger.info("Найдено {} записей для анализа", len(test_records))

    # Результаты
    full_reports: list[Any] = []
    brief_reports: list[dict[str, Any]] = []

    total_expected = 0
    total_extracted = 0

    for idx, record in enumerate(test_records, 1):
        path_part = record["path_part"]
        expected_count = record["count"]

        logger.info(
            "[{}/{}] Обработка записи: {}\n  Ожидаемое: {}",
            idx,
            len(test_records),
            path_part[:80] + "..." if len(path_part) > 80 else path_part,
            expected_count,
        )

        # Ищем файл
        file_path = find_file_in_downloads(path_part, root_dir)

        if not file_path:
            full_reports.append(
                {
                    "file_path": path_part,
                    "file_name": "NOT_FOUND",
                    "file_size": 0,
                    "parse_result": None,
                    "note": "Файл не найден в downloads/",
                }
            )

            brief_reports.append(
                {
                    "file": "NOT_FOUND",
                    "count_extracted": None,
                    "method": None,
                    "confidence": None,
                    "parse_success": False,
                    "error": "file_not_found",
                }
            )

            continue

        logger.debug("Найдено: {}", file_path)
        total_expected += 1

        # Запускаем тестовый парсинг
        parse_result = parse_file_test(file_path)

        # Сохраняем полные и краткие отчёты
        full_reports.append(generate_full_report(file_path, parse_result))
        brief_reports.append(parse_result)

        # Считаем статистику
        if parse_result["parse_success"]:
            total_extracted += 1
            logger.success(
                "  {} ✓ (извлечено: {} {} {})",
                file_path.name[:50],
                parse_result["extracted_count"],
                parse_result["method"],
                parse_result["confidence"],
            )
        else:
            logger.success(
                "  {} ✗ (ошибка: {})",
                file_path.name[:50],
                parse_result["error"][:100]
                if parse_result["error"]
                else "не определено",
            )

    # Создаём итоговый JSON
    json_data = {
        "meta": {
            "total_records": len(test_records),
            "files_found": total_expected,
            "files_parsed": total_expected,
            "files_with_extraction": total_extracted,
            "extraction_rate": (total_extracted / total_expected * 100)
            if total_expected > 0
            else 0,
        },
        "brief_reports": brief_reports,
        "full_reports": full_reports,
    }

    # Пишем JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    logger.success(
        "Результаты сохранены в: {}",
        json_path,
    )
    logger.success(
        "Итоговая статистика:\n"
        "  Записей в тестах: {}\n"
        "  Файлов найдено: {}\n"
        "  Файлов распаршено: {}\n"
        "  Успешно извлечено: {}\n"
        "  Процент успешных: {:.1f}%",
        len(test_records),
        total_expected,
        total_expected,
        total_extracted,
        (total_extracted / total_expected * 100) if total_expected > 0 else 0,
    )


if __name__ == "__main__":
    main()
