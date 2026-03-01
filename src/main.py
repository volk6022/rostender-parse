"""Точка входа Rostender Parser — CLI."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

from loguru import logger

from src.config import (
    DATA_DIR,
    DOWNLOADS_DIR,
    REPORTS_DIR,
    SEARCH_KEYWORDS as DEFAULT_KEYWORDS,
    EXCLUDE_KEYWORDS,
    MIN_PRICE_ACTIVE as DEFAULT_MIN_PRICE_ACTIVE,
    MIN_PRICE_RELATED as DEFAULT_MIN_PRICE_RELATED,
    MIN_PRICE_HISTORICAL as DEFAULT_MIN_PRICE_HISTORICAL,
    HISTORICAL_TENDERS_LIMIT as DEFAULT_HISTORY_LIMIT,
    MAX_PARTICIPANTS_THRESHOLD as DEFAULT_MAX_PARTICIPANTS,
    COMPETITION_RATIO_THRESHOLD as DEFAULT_RATIO_THRESHOLD,
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
from src.scraper.historical_search import (
    search_historical_tenders,
    extract_keywords_from_title,
)
from src.scraper.browser import create_browser, create_page
from src.scraper.auth import login
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


def _parse_args() -> argparse.Namespace:
    """Парсинг аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Rostender Parser — поиск и анализ тендеров",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--keywords",
        "-k",
        nargs="+",
        default=None,
        help="Ключевые слова для поиска (через пробел)",
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
        help="Дата поиска ОТ (DD.MM.YYYY). По умолчанию: последние 7 дней",
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
        "--dry-run",
        action="store_true",
        help="Без браузера, только показать параметры",
    )

    return parser.parse_args()


def _resolve_dates(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Определить даты поиска на основе аргументов."""
    if args.date_from or args.date_to:
        return args.date_from, args.date_to

    date_to = datetime.now().strftime("%d.%m.%Y")
    date_from = (datetime.now() - timedelta(days=args.days_back)).strftime("%d.%m.%Y")
    return date_from, date_to


async def run() -> None:
    """Главный асинхронный pipeline."""
    args = _parse_args()

    keywords = args.keywords if args.keywords else DEFAULT_KEYWORDS
    min_price_active = (
        args.min_price if args.min_price is not None else DEFAULT_MIN_PRICE_ACTIVE
    )
    min_price_related = (
        args.min_price_related
        if args.min_price_related is not None
        else DEFAULT_MIN_PRICE_RELATED
    )
    min_price_historical = (
        args.min_price_historical
        if args.min_price_historical is not None
        else DEFAULT_MIN_PRICE_HISTORICAL
    )
    history_limit = (
        args.history_limit if args.history_limit is not None else DEFAULT_HISTORY_LIMIT
    )
    max_participants = (
        args.max_participants
        if args.max_participants is not None
        else DEFAULT_MAX_PARTICIPANTS
    )
    ratio_threshold = (
        args.ratio_threshold
        if args.ratio_threshold is not None
        else DEFAULT_RATIO_THRESHOLD
    )
    date_from, date_to = _resolve_dates(args)

    _configure_logging()
    _ensure_dirs()

    logger.info("=== Rostender Parser запущен ===")
    logger.info(
        "Параметры: keywords={}, min_price={}, history_limit={}, "
        "max_participants={}, ratio_threshold={}, formats={}, date={}-{}",
        len(keywords),
        f"{min_price_active:_}",
        history_limit,
        max_participants,
        ratio_threshold,
        OUTPUT_FORMATS,
        date_from or "default",
        date_to or "default",
    )

    if args.dry_run:
        logger.info("DRY RUN: параметры показаны, выход")
        return

    # Шаг 0: Инициализация БД
    await init_db()

    # ── Один браузер и одна страница на весь pipeline ────────────────────────
    async with create_browser() as browser:
        async with create_page(browser) as page:
            # Авторизация (один раз, сессия сохраняется на весь pipeline)
            await login(page)

            # ── Этап 1: Поиск активных тендеров ──────────────────────────────
            logger.info("Этап 1: Поиск активных тендеров")

            # 1.1 Поиск списка активных тендеров
            active_tenders = await search_active_tenders(
                page,
                keywords=keywords,
                min_price=min_price_active,
                date_from=date_from,
                date_to=date_to,
            )
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

            # ── Этап 2: Анализ истории заказчиков ────────────────────────────
            logger.info("Этап 2: Поиск завершённых тендеров по ИНН заказчиков")
            async with get_connection() as conn:
                new_customers = await get_customers_by_status(conn, "new")
            logger.info(f"Заказчиков со статусом 'new': {len(new_customers)}")

            if new_customers:
                async with get_connection() as conn:
                    for customer in new_customers:
                        inn = customer["inn"]
                        name = customer["name"] or inn
                        logger.info(f"Обработка заказчика {name} (ИНН {inn})...")

                        # 2.1 Обновляем статус → processing
                        await update_customer_status(conn, inn, "processing")
                        await conn.commit()

                        try:
                            # 2.2 Получаем активные тендеры заказчика для анализа
                            active_tenders_list = await get_tenders_by_customer(
                                conn, inn, tender_status="active"
                            )

                            if not active_tenders_list:
                                logger.info(f"Нет активных тендеров для ИНН {inn}")
                                await update_customer_status(conn, inn, "analyzed")
                                await conn.commit()
                                continue

                            # 2.3 Для каждого активного тендера - свой анализ по ключевым словам из заголовка
                            for active_tender in active_tenders_list:
                                tender_id = active_tender["tender_id"]
                                tender_title = active_tender["title"] or ""

                                logger.info(
                                    f"Анализ тендера {tender_id}: '{tender_title[:50]}...'"
                                )

                                # Извлекаем ключевые слова из заголовка тендера
                                custom_kw = extract_keywords_from_title(tender_title)
                                if custom_kw:
                                    logger.debug(
                                        f"Ключевые слова для поиска: {custom_kw[:3]}..."
                                    )

                                # Поиск завершённых тендеров по кастомным ключевым словам
                                historical = await search_historical_tenders(
                                    page,
                                    inn,
                                    limit=history_limit,
                                    custom_keywords=custom_kw,
                                    min_price=min_price_historical,
                                )

                                if not historical:
                                    logger.info(
                                        f"Исторические тендеры не найдены для {tender_id}"
                                    )
                                    continue

                                logger.info(
                                    f"Найдено {len(historical)} завершённых тендеров для {tender_id}"
                                )

                                # Сохраняем завершённые тендеры
                                historical_ids = []
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
                                    historical_ids.append(t_data["tender_id"])
                                await conn.commit()

                                # Парсинг протоколов
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

                                # Получаем анализы ТОЛЬКО для этих исторических тендеров
                                analyses = await get_latest_protocol_analyses(
                                    conn, inn, historical_ids
                                )
                                metrics = calculate_metrics(analyses)
                                log_metrics(inn, metrics)

                                # Проверяем, нет ли уже результата для этого тендера
                                if await result_exists(conn, tender_id):
                                    logger.debug(
                                        f"Результат для тендера {tender_id} уже существует"
                                    )
                                    continue

                                # Сохраняем результат для этого конкретного тендера
                                if metrics.is_determinable:
                                    await insert_result(
                                        conn,
                                        active_tender_id=tender_id,
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
                                        f"Результат для тендера {tender_id}: "
                                        f"is_interesting={metrics.is_interesting}"
                                    )

                            await update_customer_status(conn, inn, "analyzed")
                            await conn.commit()
                            logger.success(f"Заказчик {inn}: анализ завершён")

                        except Exception as exc:
                            logger.error(f"Ошибка при обработке ИНН {inn}: {exc}")
                            await update_customer_status(conn, inn, "error")
                            await conn.commit()
            else:
                logger.info("Нет заказчиков для анализа (статус 'new')")

            # ── Этап 3: Расширенный поиск по интересным заказчикам ────────────
            logger.info("Этап 3: Расширенный поиск по интересным заказчикам")

            async with get_connection() as conn:
                interesting_customers = await get_interesting_customers(conn)
            logger.info(
                f"Интересных заказчиков для расширенного поиска: {len(interesting_customers)}"
            )

            if interesting_customers:
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
                            keywords=keywords,
                            min_price=min_price_related,
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

                            # Извлекаем ключевые слова из заголовка тендера
                            tender_title = t_data["title"] or ""
                            custom_kw = extract_keywords_from_title(tender_title)
                            if custom_kw:
                                logger.debug(
                                    f"Ключевые слова для тендера {t_data['tender_id']}: {custom_kw[:3]}..."
                                )

                            try:
                                # Поиск завершённых тендеров с кастомными ключевыми словами
                                historical = await search_historical_tenders(
                                    page,
                                    inn,
                                    limit=history_limit,
                                    custom_keywords=custom_kw,
                                    min_price=min_price_historical,
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

    # ── Этап 4: Формирование отчёта (без браузера) ───────────────────────────
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
