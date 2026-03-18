"""Этап 3: Расширенный поиск по интересным заказчикам."""

from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

from src.db.repository import (
    get_connection,
    get_customer_metrics,
    get_interesting_customers,
    insert_result,
    result_exists,
    tender_exists,
    update_customer_status,
    upsert_tender,
)
from src.scraper.active_tenders import search_tenders_by_inn
from src.stages.params import PipelineParams
from src.utils.monitoring import StageStats, timed_operation


async def run_extended_search(page: Page, params: PipelineParams) -> None:
    """Этап 3: Расширенный поиск по интересным заказчикам.

    Выполняет:
      3.1  Получение интересных заказчиков из БД
      3.2  Поиск всех активных тендеров заказчика (цена >= min_price_related)
      3.3  Для каждого нового тендера — копирование метрик из первичного анализа
      3.4  Сохранение результатов (source=extended, is_interesting=True)

    Зависимости данных: требует results с is_interesting=True (Этап 2).
    """
    logger.info("Этап 3: Расширенный поиск по интересным заказчикам")
    stats = StageStats("Этап 3 (Расширенный поиск)")

    async with get_connection() as conn:
        interesting_customers = await get_interesting_customers(conn)
    logger.info(
        f"Интересных заказчиков для расширенного поиска: {len(interesting_customers)}"
    )

    if not interesting_customers:
        logger.info("Этап 3: Нет интересных заказчиков, пропуск")
        return

    for customer in interesting_customers:
        inn = customer["inn"]
        name = customer["name"] or inn
        logger.info(f"Расширенный поиск для заказчика {name} (ИНН {inn})...")

        async with get_connection() as conn:
            # Получаем метрики "интересности" этого заказчика
            metrics = await get_customer_metrics(conn, inn)
            if not metrics:
                logger.warning(f"Метрики для ИНН {inn} не найдены, пропуск")
                continue

        # 3.1 Найти ВСЕ активные тендеры заказчика (цена >= min_price_related)
        try:
            with timed_operation(f"Поиск тендеров ИНН {inn}"):
                extended_tenders = await search_tenders_by_inn(
                    page,
                    inn,
                    keywords=params.keywords,
                    exclude_keywords=params.exclude_keywords,
                    min_price=params.min_price_related,
                )
        except Exception as search_err:
            logger.error(f"Ошибка поиска тендеров для ИНН {inn}: {search_err}")
            stats.add(success=False)
            continue

        if not extended_tenders:
            logger.info(
                f"Для ИНН {inn} новых тендеров >= {params.min_price_related} не найдено"
            )
            stats.add(success=True)
            continue

        logger.info(f"Найдено {len(extended_tenders)} активных тендеров для ИНН {inn}")

        async with get_connection() as conn:
            # Обновляем статус заказчика на extended_processing
            await update_customer_status(conn, inn, "extended_processing")
            await conn.commit()

            customer_success = True
            for t_data in extended_tenders:
                tender_id = t_data["tender_id"]

                # Проверяем, не обрабатывали ли мы уже этот тендер
                if await tender_exists(conn, tender_id):
                    logger.debug(f"Тендер {tender_id} уже в базе, пропускаем")
                    continue

                # 3.2 Сохраняем новый активный тендер
                logger.info(f"Добавление нового тендера {tender_id}...")
                try:
                    await upsert_tender(
                        conn,
                        tender_id=tender_id,
                        customer_inn=inn,
                        session_id=params.session_id,
                        url=t_data["url"],
                        title=t_data["title"],
                        price=t_data["price"],
                        tender_status="active",
                    )

                    # 3.3 Копируем метрики и помечаем как интересный
                    if not await result_exists(conn, tender_id):
                        await insert_result(
                            conn,
                            active_tender_id=tender_id,
                            customer_inn=inn,
                            session_id=params.session_id,
                            total_historical=metrics["total_historical"],
                            total_analyzed=metrics["total_analyzed"],
                            total_skipped=metrics["total_skipped"],
                            low_competition_count=metrics["low_competition_count"],
                            competition_ratio=metrics["competition_ratio"],
                            is_interesting=True,
                            source="extended",
                        )

                    await conn.commit()
                except Exception as exc:
                    logger.error(f"Ошибка при добавлении тендера {tender_id}: {exc}")
                    customer_success = False

            # Обновляем статус заказчика после завершения
            await update_customer_status(conn, inn, "extended_analyzed")
            await conn.commit()
            stats.add(success=customer_success)

    stats.log_final()
    logger.info("Этап 3: Расширенный поиск завершён")

    stats.log_final()
    logger.info("Этап 3: Расширенный поиск завершён")
