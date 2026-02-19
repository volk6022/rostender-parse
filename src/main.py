"""Точка входа Rostender Parser — CLI."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from src.config import (
    DATA_DIR,
    DOWNLOADS_DIR,
    REPORTS_DIR,
    SEARCH_KEYWORDS,
    EXCLUDE_KEYWORDS,
    MIN_PRICE_ACTIVE,
    HISTORICAL_TENDERS_LIMIT,
    MAX_PARTICIPANTS_THRESHOLD,
    COMPETITION_RATIO_THRESHOLD,
    OUTPUT_FORMATS,
)
from src.db.repository import (
    get_connection,
    init_db,
    upsert_customer,
    upsert_tender,
)
from src.scraper.active_tenders import extract_inn_from_page, search_active_tenders
from src.scraper.browser import create_browser, create_page


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


async def run() -> None:
    """Главный асинхронный pipeline."""
    _configure_logging()
    _ensure_dirs()

    logger.info("=== Rostender Parser запущен ===")
    logger.info(
        "Параметры: keywords={}, min_price={}, history_limit={}, "
        "max_participants={}, ratio_threshold={}, formats={}",
        len(SEARCH_KEYWORDS),
        f"{MIN_PRICE_ACTIVE:_}",
        HISTORICAL_TENDERS_LIMIT,
        MAX_PARTICIPANTS_THRESHOLD,
        COMPETITION_RATIO_THRESHOLD,
        OUTPUT_FORMATS,
    )

    # Шаг 0: Инициализация БД
    await init_db()

    # Шаг 1: Поиск активных тендеров
    logger.info("Этап 1: Поиск активных тендеров")
    async with create_browser() as browser:
        async with create_page(browser) as page:
            # 1.1 Поиск списка активных тендеров
            active_tenders = await search_active_tenders(page)
            logger.info(f"Найдено активных тендеров: {len(active_tenders)}")

            async with await get_connection() as conn:
                for t_data in active_tenders:
                    # 1.2 Для каждого тендера заходим внутрь для извлечения ИНН
                    logger.info(f"Обработка тендера {t_data['tender_id']}...")
                    inn = await extract_inn_from_page(page, t_data["url"])

                    if not inn:
                        logger.warning(
                            f"Пропуск тендера {t_data['tender_id']} (ИНН не найден)"
                        )
                        continue

                    # 1.3 Сохраняем в БД
                    await upsert_customer(conn, inn=inn)
                    await upsert_tender(
                        conn,
                        tender_id=t_data["tender_id"],
                        customer_inn=inn,
                        url=t_data["url"],
                        title=t_data["title"],
                        price=t_data["price"],
                        tender_status="active",
                    )
                    await conn.commit()
                    logger.success(f"Тендер {t_data['tender_id']} (ИНН {inn}) сохранен")

    # Шаг 2: Анализ истории заказчиков
    # TODO: Этап 3 — scraper/historical_search.py + parser/*
    logger.info("Этап 2: Анализ истории заказчиков — ещё не реализован")

    # Шаг 3: Расширенный поиск по интересным заказчикам
    # TODO: Этап 7
    logger.info("Этап 3: Расширенный поиск — ещё не реализован")

    # Шаг 4: Формирование отчёта
    # TODO: Этап 8 — reporter/*
    logger.info("Этап 4: Отчёт — ещё не реализован")

    logger.info("=== Rostender Parser завершён ===")


def main() -> None:
    """Синхронная обёртка для CLI."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
