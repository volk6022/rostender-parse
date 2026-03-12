"""Точка входа Rostender Parser — CLI с субкомандами."""

from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger

from src.config import (
    DATA_DIR,
    DOWNLOADS_DIR,
    REPORTS_DIR,
    ConfigError,
    validate_config,
)
from src.db.repository import init_db
from src.scraper.auth import login
from src.scraper.browser import create_browser, create_page
from src.stages.analyze_history import run_analyze_history
from src.stages.extended_search import run_extended_search
from src.stages.params import PipelineParams
from src.stages.report import run_report, run_active_report
from src.stages.search_active import run_search_active


# ── Инфраструктура ───────────────────────────────────────────────────────────


def _configure_logging() -> None:
    """Настроить loguru: формат, уровень, ротация."""
    logger.remove()
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        level="INFO",
    )
    logger.add(
        DATA_DIR / "rostender.log",
        rotation="5 MB",
        retention="7 days",
        level="DEBUG",
    )


def _ensure_dirs() -> None:
    """Создать необходимые директории, если их нет."""
    for d in (DATA_DIR, DOWNLOADS_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Добавить общие аргументы, доступные всем субкомандам."""
    parser.add_argument(
        "--keywords",
        "-k",
        nargs="+",
        default=None,
        help="Ключевые слова для поиска (через пробел)",
    )
    parser.add_argument(
        "--exclude-keywords",
        "-e",
        nargs="+",
        default=None,
        help="Слова-исключения для поиска (через пробел)",
    )
    parser.add_argument(
        "--min-price",
        "-p",
        type=int,
        default=None,
        help="Мин. цена активных тендеров в руб.",
    )
    parser.add_argument(
        "--min-price-related",
        type=int,
        default=None,
        help="Мин. цена для расширенного поиска заказчика в руб.",
    )
    parser.add_argument(
        "--min-price-historical",
        type=int,
        default=None,
        help="Мин. цена для исторического поиска в руб.",
    )
    parser.add_argument(
        "--history-limit",
        "-l",
        type=int,
        default=None,
        help="Кол-во завершённых тендеров для анализа",
    )
    parser.add_argument(
        "--max-participants",
        "-m",
        type=int,
        default=None,
        help="Макс. кол-во участников для низкой конкуренции",
    )
    parser.add_argument(
        "--ratio-threshold",
        "-r",
        type=float,
        default=None,
        help="Доля тендеров с низкой конкуренцией (0.0-1.0)",
    )
    parser.add_argument(
        "--date-from",
        type=str,
        default=None,
        help="Дата поиска ОТ (DD.MM.YYYY). По умолчанию: последние N дней",
    )
    parser.add_argument(
        "--date-to",
        type=str,
        default=None,
        help="Дата поиска ДО (DD.MM.YYYY). По умолчанию: сегодня",
    )
    parser.add_argument(
        "--days-back",
        "-d",
        type=int,
        default=7,
        help="Искать за последние N дней (если не указаны --date-from/--date-to)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        # type=bool,
        default=False,
        help="Показывать окно браузера (по умолчанию headless=True)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        # type=bool,
        help="Без браузера, только показать параметры",
    )


def _parse_args() -> argparse.Namespace:
    """Парсинг аргументов командной строки с субкомандами."""
    parser = argparse.ArgumentParser(
        description="Rostender Parser — поиск и анализ тендеров",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  rostender                          # Full pipeline (stages 1-4)\n"
            "  rostender search-active            # Stage 1 only\n"
            "  rostender analyze-history          # Stage 2 only\n"
            "  rostender extended-search          # Stage 3 only\n"
            "  rostender report                   # Stage 4 only (no browser)\n"
            "  rostender report-active            # Generate active tenders report\n"
            "  rostender --dry-run                # Show params, no execution\n"
            "  rostender search-active -k keyword1 keyword2 --min-price 10000000\n"
        ),
    )

    # Общие аргументы на верхнем уровне (для `rostender --dry-run` и т.п.)
    _add_common_args(parser)

    subparsers = parser.add_subparsers(dest="command", help="Этап pipeline для запуска")

    # run — полный pipeline (явный вызов)
    run_parser = subparsers.add_parser(
        "run",
        help="Полный pipeline (этапы 1-4)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_common_args(run_parser)

    # search-active — Этап 1
    s1 = subparsers.add_parser(
        "search-active",
        help="Этап 1: Поиск активных тендеров + извлечение ИНН",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_common_args(s1)

    # analyze-history — Этап 2
    s2 = subparsers.add_parser(
        "analyze-history",
        help="Этап 2: Анализ истории заказчиков (завершённые тендеры + протоколы)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_common_args(s2)

    # extended-search — Этап 3
    s3 = subparsers.add_parser(
        "extended-search",
        help="Этап 3: Расширенный поиск по интересным заказчикам",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_common_args(s3)

    # report — Этап 4
    s4 = subparsers.add_parser(
        "report",
        help="Этап 4: Генерация отчёта (без браузера)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_common_args(s4)

    # report-active — Дополнительный отчёт по активным тендерам
    s_active = subparsers.add_parser(
        "report-active",
        help="Генерация Excel со списком активных тендеров",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_common_args(s_active)

    args = parser.parse_args()

    # Если субкоманда не указана — полный pipeline
    if args.command is None:
        args.command = "run"

    # --no-headless → headless (инверсия для удобства PipelineParams)
    args.headless = not args.no_headless

    return args


# ── Диспетчер ────────────────────────────────────────────────────────────────


async def run() -> None:
    """Главный асинхронный dispatcher."""
    args = _parse_args()
    params = PipelineParams.from_args(args)
    command = args.command

    _configure_logging()
    _ensure_dirs()

    logger.info("=== Rostender Parser запущен ===")
    logger.info(
        "Команда: {}, keywords={}, exclude={}, min_price={}, history_limit={}, "
        "max_participants={}, ratio_threshold={}, formats={}, date={}-{}",
        command,
        len(params.keywords),
        len(params.exclude_keywords),
        f"{params.min_price_active:_}",
        params.history_limit,
        params.max_participants,
        params.ratio_threshold,
        params.output_formats,
        params.date_from or "default",
        params.date_to or "default",
    )

    if args.dry_run:
        logger.info("DRY RUN: параметры показаны, выход")
        return

    # Валидация конфигурации (бросит ConfigError если config.yaml не в порядке)
    validate_config()

    # Инициализация БД
    await init_db()

    if command == "run":
        # Полный pipeline: один браузер, одна сессия, все этапы
        async with create_browser(headless=params.headless) as browser:
            async with create_page(browser) as page:
                await login(page)
                await run_search_active(page, params)
                await run_analyze_history(page, params)
                await run_extended_search(page, params)
        await run_report(params)

    elif command == "report":
        # Отчёт: браузер не нужен
        await run_report(params)

    elif command == "report-active":
        # Отчёт по активным: браузер не нужен
        await run_active_report(params)

    elif command in ("search-active", "analyze-history", "extended-search"):
        # Отдельный этап: собственная браузерная сессия
        async with create_browser(headless=params.headless) as browser:
            async with create_page(browser) as page:
                await login(page)
                if command == "search-active":
                    await run_search_active(page, params)
                elif command == "analyze-history":
                    await run_analyze_history(page, params)
                elif command == "extended-search":
                    await run_extended_search(page, params)

    logger.info("=== Rostender Parser завершён ===")


def main() -> None:
    """Синхронная обёртка для CLI."""
    # Windows cp1252 не поддерживает кириллицу — переключаем на UTF-8
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

    asyncio.run(run())


if __name__ == "__main__":
    main()
