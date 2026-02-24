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
    MIN_PRICE_RELATED,
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
    get_customers_by_status,
    get_tenders_by_customer,
    update_customer_status,
    insert_result,
    get_protocol_analyses_for_customer,
    get_interesting_customers,
    tender_exists,
    result_exists,
    get_latest_protocol_analyses,
    get_interesting_results,
    get_all_customers,
    get_all_results,
    get_all_protocol_analyses,
)
from src.scraper.active_tenders import (
    extract_inn_from_page,
    get_customer_name,
    search_active_tenders,
    search_tenders_by_inn,
)
from src.scraper.historical_search import search_historical_tenders
from src.scraper.browser import create_browser, create_page
from src.scraper.eis_fallback import fallback_extract_inn
from src.parser.html_protocol import analyze_tender_protocol
from src.analyzer.competition import calculate_metrics, log_metrics
from src.reporter.console_report import print_console_report, log_console_summary
from src.reporter.excel_report import generate_excel_report


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

            async with get_connection() as conn:
                for t_data in active_tenders:
                    # 1.2 Для каждого тендера заходим внутрь для извлечения ИНН
                    logger.info(f"Обработка тендера {t_data['tender_id']}...")
                    inn = await extract_inn_from_page(page, t_data["url"])

                    if not inn:
                        logger.info("ИНН не найден на rostender.info, пробуем ЕИС...")
                        inn = await fallback_extract_inn(page, t_data["url"])

                    if not inn:
                        logger.warning(
                            f"Пропуск тендера {t_data['tender_id']} (ИНН не найден)"
                        )
                        continue

                    # 1.3 Извлекаем имя заказчика (страница уже загружена после extract_inn)
                    customer_name = await get_customer_name(page)

                    # 1.4 Сохраняем в БД
                    await upsert_customer(conn, inn=inn, name=customer_name)
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
    logger.info("Этап 2: Поиск завершённых тендеров по ИНН заказчиков")
    async with get_connection() as conn:
        new_customers = await get_customers_by_status(conn, "new")
    logger.info(f"Заказчиков со статусом 'new': {len(new_customers)}")

    if new_customers:
        async with create_browser() as browser:
            async with create_page(browser) as page:
                async with get_connection() as conn:
                    for customer in new_customers:
                        inn = customer["inn"]
                        name = customer["name"] or inn
                        logger.info(f"Обработка заказчика {name} (ИНН {inn})...")

                        # 2.1 Обновляем статус → processing
                        await update_customer_status(conn, inn, "processing")
                        await conn.commit()

                        try:
                            # 2.2 Поиск завершённых тендеров
                            historical = await search_historical_tenders(
                                page, inn, limit=HISTORICAL_TENDERS_LIMIT
                            )
                            logger.info(
                                f"Найдено завершённых тендеров для ИНН {inn}: "
                                f"{len(historical)}"
                            )

                            # 2.3 Сохраняем завершённые тендеры в БД
                            for t_data in historical:
                                await upsert_tender(
                                    conn,
                                    tender_id=t_data["tender_id"],
                                    customer_inn=inn,
                                    url=t_data["url"],
                                    title=t_data["title"],
                                    price=t_data["price"],
                                    tender_status="completed",
                                )
                            await conn.commit()

                            # 2.4 Парсинг протоколов для каждого завершённого тендера
                            logger.info(
                                f"Парсинг протоколов для ИНН {inn} "
                                f"({len(historical)} тендеров)..."
                            )
                            success_count = 0
                            failed_count = 0

                            for t_data in historical:
                                try:
                                    result = await analyze_tender_protocol(
                                        page=page,
                                        tender_id=t_data["tender_id"],
                                        tender_url=t_data["url"],
                                        customer_inn=inn,
                                        conn=conn,
                                    )
                                    if result.parse_status == "success":
                                        success_count += 1
                                    else:
                                        failed_count += 1
                                except Exception as proto_exc:
                                    logger.error(
                                        f"Ошибка парсинга протокола тендера "
                                        f"{t_data['tender_id']}: {proto_exc}"
                                    )
                                    failed_count += 1

                            logger.info(
                                f"ИНН {inn}: протоколы проанализированы — "
                                f"success={success_count}, failed/skipped={failed_count}"
                            )

                            analyses = await get_protocol_analyses_for_customer(
                                conn, inn
                            )
                            metrics = calculate_metrics(analyses)
                            log_metrics(inn, metrics)

                            if metrics.is_determinable:
                                active_tenders_for_inn = await get_tenders_by_customer(
                                    conn, inn, tender_status="active"
                                )
                                for active_tender in active_tenders_for_inn:
                                    await insert_result(
                                        conn,
                                        active_tender_id=active_tender["tender_id"],
                                        customer_inn=inn,
                                        total_historical=metrics.total_historical,
                                        total_analyzed=metrics.total_analyzed,
                                        total_skipped=metrics.total_skipped,
                                        low_competition_count=metrics.low_competition_count,
                                        competition_ratio=metrics.competition_ratio,
                                        is_interesting=metrics.is_interesting,
                                        source="primary",
                                    )
                                await conn.commit()
                                logger.success(
                                    f"Результаты сохранены для INN {inn}: "
                                    f"is_interesting={metrics.is_interesting}"
                                )

                            await update_customer_status(conn, inn, "analyzed")
                            await conn.commit()
                            logger.success(
                                f"Заказчик {inn}: сохранено "
                                f"{len(historical)} завершённых тендеров, "
                                f"протоколов проанализировано: {success_count}"
                            )

                        except Exception as exc:
                            logger.error(f"Ошибка при обработке ИНН {inn}: {exc}")
                            await update_customer_status(conn, inn, "error")
                            await conn.commit()
    else:
        logger.info("Нет заказчиков для анализа (статус 'new')")

    # Шаг 3: Расширенный поиск по интересным заказчикам (Этап 7)
    logger.info("Этап 3: Расширенный поиск по интересным заказчикам")

    async with get_connection() as conn:
        interesting_customers = await get_interesting_customers(conn)
    logger.info(
        f"Интересных заказчиков для расширенного поиска: {len(interesting_customers)}"
    )

    if interesting_customers:
        async with create_browser() as browser:
            async with create_page(browser) as page:
                for customer in interesting_customers:
                    inn = customer["inn"]
                    name = customer["name"] or inn
                    logger.info(
                        f"Расширенный поиск для заказчика {name} (ИНН {inn})..."
                    )

                    # 3.1 Найти ВСЕ активные тендеры заказчика (цена ≥ 2M)
                    try:
                        extended_tenders = await search_tenders_by_inn(
                            page,
                            inn,
                            min_price=MIN_PRICE_RELATED,
                        )
                    except Exception as search_err:
                        logger.error(
                            f"Ошибка поиска тендеров для ИНН {inn}: {search_err}"
                        )
                        continue

                    if not extended_tenders:
                        logger.info(f"Для ИНН {inn} новых тендеров ≥ 2M не найдено")
                        continue

                    logger.info(
                        f"Найдено {len(extended_tenders)} новых тендеров для ИНН {inn}"
                    )

                    async with get_connection() as conn:
                        # Обновляем статус заказчика на processing
                        await update_customer_status(conn, inn, "extended_processing")
                        await conn.commit()

                        for t_data in extended_tenders:
                            # Проверяем, не обрабатывали ли мы уже этот тендер
                            if await tender_exists(conn, t_data["tender_id"]):
                                logger.debug(
                                    f"Тендер {t_data['tender_id']} уже в базе, пропускаем"
                                )
                                continue

                            # Bug #2 fix: проверяем, нет ли уже результата для этого тендера
                            if await result_exists(conn, t_data["tender_id"]):
                                logger.debug(
                                    f"Результат для тендера {t_data['tender_id']} "
                                    f"уже существует, пропускаем"
                                )
                                continue

                            # 3.2 Сохраняем новый активный тендер
                            logger.info(
                                f"Обработка нового тендера {t_data['tender_id']}..."
                            )
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

                            # 3.3 Анализ истории для нового тендера (как в Этапе 2)
                            new_historical_ids: list[str] = []

                            try:
                                # Поиск завершённых тендеров
                                historical = await search_historical_tenders(
                                    page, inn, limit=HISTORICAL_TENDERS_LIMIT
                                )

                                if not historical:
                                    logger.warning(
                                        f"Для тендера {t_data['tender_id']} "
                                        f"исторических тендеров не найдено"
                                    )
                                    continue

                                for h_data in historical:
                                    await upsert_tender(
                                        conn,
                                        tender_id=h_data["tender_id"],
                                        customer_inn=inn,
                                        url=h_data["url"],
                                        title=h_data["title"],
                                        price=h_data["price"],
                                        tender_status="completed",
                                    )
                                    new_historical_ids.append(h_data["tender_id"])
                                await conn.commit()

                                # Парсинг протоколов
                                success_count = 0
                                failed_count = 0

                                for h_data in historical:
                                    try:
                                        result = await analyze_tender_protocol(
                                            page=page,
                                            tender_id=h_data["tender_id"],
                                            tender_url=h_data["url"],
                                            customer_inn=inn,
                                            conn=conn,
                                        )
                                        if result.parse_status == "success":
                                            success_count += 1
                                        else:
                                            failed_count += 1
                                    except Exception as proto_exc:
                                        logger.error(
                                            f"Ошибка парсинга протокола тендера "
                                            f"{h_data['tender_id']}: {proto_exc}"
                                        )
                                        failed_count += 1

                                # Bug #1 fix: Расчёт метрик ТОЛЬКО для вновь проанализированных тендеров
                                # Bug #3 fix: Передаём только новые tender_ids
                                if new_historical_ids:
                                    analyses = await get_latest_protocol_analyses(
                                        conn, inn, new_historical_ids
                                    )
                                else:
                                    analyses = []

                                metrics = calculate_metrics(analyses)
                                log_metrics(inn, metrics)

                                # Bug #2 fix: Сохраняем результат только если его ещё нет
                                if metrics.is_determinable:
                                    await insert_result(
                                        conn,
                                        active_tender_id=t_data["tender_id"],
                                        customer_inn=inn,
                                        total_historical=metrics.total_historical,
                                        total_analyzed=metrics.total_analyzed,
                                        total_skipped=metrics.total_skipped,
                                        low_competition_count=metrics.low_competition_count,
                                        competition_ratio=metrics.competition_ratio,
                                        is_interesting=metrics.is_interesting,
                                        source="extended",
                                    )
                                    await conn.commit()
                                    logger.success(
                                        f"Результат для тендера {t_data['tender_id']} "
                                        f"(source=extended): is_interesting={metrics.is_interesting}"
                                    )

                            except Exception as exc:
                                logger.error(
                                    f"Ошибка при расширенном анализе тендера "
                                    f"{t_data['tender_id']}: {exc}"
                                )

                        # Bug #4 fix: Обновляем статус заказчика после завершения
                        await update_customer_status(conn, inn, "extended_analyzed")
                        await conn.commit()

    logger.info("Этап 3: Расширенный поиск завершён")

    # Шаг 4: Формирование отчёта
    logger.info("Этап 4: Формирование отчёта...")

    async with get_connection() as conn:
        interesting_results = await get_interesting_results(conn)
        all_results = await get_all_results(conn)
        all_customers = await get_all_customers(conn)
        all_protocols = await get_all_protocol_analyses(conn)

    if "console" in OUTPUT_FORMATS:
        print_console_report(interesting_results, all_results, all_customers)
        log_console_summary(len(all_customers), len(interesting_results))

    if "excel" in OUTPUT_FORMATS:
        excel_path = generate_excel_report(
            interesting_results, all_results, all_customers, all_protocols
        )
        logger.success("Отчёт сохранён: {}", excel_path)

    logger.info("=== Rostender Parser завершён ===")


def main() -> None:
    """Синхронная обёртка для CLI."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
