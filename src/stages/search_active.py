"""Этап 1: Поиск активных тендеров, извлечение ИНН, сохранение в БД."""

from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

from src.db.repository import (
    get_connection,
    upsert_customer,
    upsert_customers_batch,
    upsert_tender,
    upsert_tenders_batch,
)
from src.scraper.active_tenders import (
    extract_inn_from_page,
    get_customer_name,
    search_active_tenders,
)
from src.scraper.unified_fallback import unified_fallback_extract_inn
from src.scraper.fallbacks.eis import fallback_extract_inn
from src.stages.params import PipelineParams
from src.stages.report import run_active_report
from src.utils.monitoring import StageStats, timed_operation


async def run_search_active(page: Page, params: PipelineParams) -> None:
    """Этап 1: Поиск активных тендеров на rostender.info.

    Выполняет:
      1.1  Поиск списка активных тендеров по фильтрам
      1.2  Для каждого тендера — извлечение ИНН заказчика
           (rostender.info → fallback на zakupki.gov.ru)
      1.3  Извлечение имени заказчика
      1.4  Сохранение тендера и заказчика в SQLite (Batch)
    """
    logger.info("Этап 1: Поиск активных тендеров")
    stats = StageStats("Этап 1 (Поиск активных)")

    # 1.1 Поиск списка активных тендеров
    with timed_operation("Первичный поиск тендеров"):
        active_tenders = await search_active_tenders(
            page,
            keywords=params.keywords,
            exclude_keywords=params.exclude_keywords,
            min_price=params.min_price_active,
            date_from=params.date_from,
            date_to=params.date_to,
        )
    logger.info(f"Найдено активных тендеров: {len(active_tenders)}")

    # Очереди для пакетной записи
    tenders_to_upsert = []
    customers_to_upsert = {}  # ИНН -> имя

    async with get_connection() as conn:
        for idx, t_data in enumerate(active_tenders):
            # 1.2 Для каждого тендера заходим внутрь для извлечения ИНН и ссылок
            logger.info(
                "Обработка тендера {}/{} ({})...",
                idx + 1,
                len(active_tenders),
                t_data["tender_id"],
            )
            try:
                inn, source_urls = await extract_inn_from_page(page, t_data["url"])

                if not inn:
                    logger.info(
                        "ИНН не найден на rostender.info, пробуем внешние площадки..."
                    )
                    inn = await unified_fallback_extract_inn(page, source_urls)

                if not inn:
                    logger.warning(
                        f"Пропуск тендера {t_data['tender_id']} (ИНН не найден)"
                    )
                    stats.add(success=False)
                    continue

                # 1.3 Извлекаем имя заказчика (страница уже загружена после extract_inn)
                customer_name = await get_customer_name(page)

                # Накапливаем данные для пакетной записи
                if inn not in customers_to_upsert or (
                    customer_name and not customers_to_upsert[inn]
                ):
                    customers_to_upsert[inn] = customer_name

                tenders_to_upsert.append(
                    {
                        "tender_id": t_data["tender_id"],
                        "customer_inn": inn,
                        "url": t_data["url"],
                        "source_urls": source_urls,
                        "title": t_data["title"],
                        "price": t_data["price"],
                        "tender_status": "active",
                    }
                )
                stats.add(success=True)
            except Exception as e:
                logger.error(
                    "Ошибка при обработке тендера {}: {}", t_data["tender_id"], e
                )
                stats.add(success=False)

            # 1.4 Сохраняем в БД пакетами каждые 10 штук или в конце
            if len(tenders_to_upsert) >= 10:
                await _flush_active_batch(conn, tenders_to_upsert, customers_to_upsert)
                tenders_to_upsert.clear()
                customers_to_upsert.clear()

        # Финальный сброс остатков
        if tenders_to_upsert:
            await _flush_active_batch(conn, tenders_to_upsert, customers_to_upsert)

    stats.log_final()
    logger.info("Этап 1: завершён")

    # Генерируем Excel-отчёт со списком активных тендеров
    await run_active_report(params)


async def _flush_active_batch(conn, tenders, customers):
    """Вспомогательная функция для записи пакета в БД."""
    if customers:
        cust_list = [{"inn": inn, "name": name} for inn, name in customers.items()]
        await upsert_customers_batch(conn, cust_list)

    if tenders:
        await upsert_tenders_batch(conn, tenders)

    await conn.commit()
    logger.debug(f"Пакет из {len(tenders)} тендеров сохранен в БД")
