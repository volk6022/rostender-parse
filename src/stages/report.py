"""Этап 4: Генерация отчётов (console + Excel). Браузер НЕ нужен."""

from __future__ import annotations

from loguru import logger

from src.db.repository import (
    get_all_customers,
    get_all_protocol_analyses,
    get_all_results,
    get_connection,
    get_interesting_results,
)
from src.reporter.console_report import log_console_summary, print_console_report
from src.reporter.excel_report import generate_excel_report
from src.stages.params import PipelineParams


async def run_report(params: PipelineParams) -> None:
    """Этап 4: Формирование отчёта по данным из БД.

    Выполняет:
      4.1  Чтение всех данных из SQLite
      4.2  Вывод в консоль (если ``console`` в output_formats)
      4.3  Генерация Excel-файла (если ``excel`` в output_formats)

    Зависимости данных: требует данные в БД (Этапы 1-3).
    Браузер НЕ требуется.
    """
    logger.info("Этап 4: Формирование отчёта...")

    async with get_connection() as conn:
        interesting_results = await get_interesting_results(conn)
        all_results = await get_all_results(conn)
        all_customers = await get_all_customers(conn)
        all_protocols = await get_all_protocol_analyses(conn)

    if "console" in params.output_formats:
        print_console_report(interesting_results, all_results, all_customers)
        log_console_summary(len(all_customers), len(interesting_results))

    if "excel" in params.output_formats:
        excel_path = generate_excel_report(
            interesting_results, all_results, all_customers, all_protocols
        )
        logger.success("Отчёт сохранён: {}", excel_path)

    logger.info("Этап 4: завершён")
