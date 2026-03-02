"""Этап 1: Поиск активных тендеров, извлечение ИНН, сохранение в БД."""

from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

from src.db.repository import get_connection, upsert_customer, upsert_tender
from src.scraper.active_tenders import (
    extract_inn_from_page,
    get_customer_name,
    search_active_tenders,
)
from src.scraper.eis_fallback import fallback_extract_inn
from src.stages.params import PipelineParams


async def run_search_active(page: Page, params: PipelineParams) -> None:
    """Этап 1: Поиск активных тендеров на rostender.info.

    Выполняет:
      1.1  Поиск списка активных тендеров по фильтрам
      1.2  Для каждого тендера — извлечение ИНН заказчика
           (rostender.info → fallback на zakupki.gov.ru)
      1.3  Извлечение имени заказчика
      1.4  Сохранение тендера и заказчика в SQLite

    Зависимости данных: нет (начальный этап).
    """
    logger.info("Этап 1: Поиск активных тендеров")

    # 1.1 Поиск списка активных тендеров
    active_tenders = await search_active_tenders(
        page,
        keywords=params.keywords,
        min_price=params.min_price_active,
        date_from=params.date_from,
        date_to=params.date_to,
    )
    logger.info(f"Найдено активных тендеров: {len(active_tenders)}")

    async with get_connection() as conn:
        for t_data in active_tenders:
            # 1.2 Для каждого тендера заходим внутрь для извлечения ИНН и ссылок
            logger.info(f"Обработка тендера {t_data['tender_id']}...")
            inn, source_urls = await extract_inn_from_page(page, t_data["url"])

            if not inn:
                logger.info("ИНН не найден на rostender.info, пробуем ЕИС...")
                inn, fallback_source_urls = await fallback_extract_inn(
                    page, t_data["url"]
                )
                if fallback_source_urls:
                    if not source_urls:
                        source_urls = fallback_source_urls
                    elif fallback_source_urls not in source_urls:
                        source_urls = f"{source_urls},{fallback_source_urls}"

            if not inn:
                logger.warning(f"Пропуск тендера {t_data['tender_id']} (ИНН не найден)")
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
                source_urls=source_urls,
                title=t_data["title"],
                price=t_data["price"],
                tender_status="active",
            )
            await conn.commit()
            logger.success(f"Тендер {t_data['tender_id']} (ИНН {inn}) сохранен")

    logger.info("Этап 1: завершён")
