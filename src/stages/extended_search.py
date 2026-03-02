"""Этап 3: Расширенный поиск по интересным заказчикам."""

from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

from src.db.repository import (
    get_connection,
    get_interesting_customers,
    result_exists,
    tender_exists,
    update_customer_status,
    upsert_tender,
)
from src.scraper.active_tenders import search_tenders_by_inn
from src.stages._history_helpers import analyze_tender_history
from src.stages.params import PipelineParams


async def run_extended_search(page: Page, params: PipelineParams) -> None:
    """Этап 3: Расширенный поиск по интересным заказчикам.

    Выполняет:
      3.1  Получение интересных заказчиков из БД
      3.2  Поиск всех активных тендеров заказчика (цена >= min_price_related)
      3.3  Для каждого нового тендера — анализ истории по ключевым словам
      3.4  Расчёт метрик, сохранение результатов (source=extended)

    Зависимости данных: требует results с is_interesting=True (Этап 2).
    """
    logger.info("Этап 3: Расширенный поиск по интересным заказчикам")

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

        # 3.1 Найти ВСЕ активные тендеры заказчика (цена >= min_price_related)
        try:
            extended_tenders = await search_tenders_by_inn(
                page,
                inn,
                keywords=params.keywords,
                min_price=params.min_price_related,
            )
        except Exception as search_err:
            logger.error(f"Ошибка поиска тендеров для ИНН {inn}: {search_err}")
            continue

        if not extended_tenders:
            logger.info(
                f"Для ИНН {inn} новых тендеров >= {params.min_price_related} не найдено"
            )
            continue

        logger.info(f"Найдено {len(extended_tenders)} новых тендеров для ИНН {inn}")

        async with get_connection() as conn:
            # Обновляем статус заказчика на extended_processing
            await update_customer_status(conn, inn, "extended_processing")
            await conn.commit()

            for t_data in extended_tenders:
                # Проверяем, не обрабатывали ли мы уже этот тендер
                if await tender_exists(conn, t_data["tender_id"]):
                    logger.debug(f"Тендер {t_data['tender_id']} уже в базе, пропускаем")
                    continue

                # Проверяем, нет ли уже результата для этого тендера
                if await result_exists(conn, t_data["tender_id"]):
                    logger.debug(
                        f"Результат для тендера {t_data['tender_id']} "
                        f"уже существует, пропускаем"
                    )
                    continue

                # 3.2 Сохраняем новый активный тендер
                logger.info(f"Обработка нового тендера {t_data['tender_id']}...")
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

                # 3.3 Анализ истории для нового тендера
                try:
                    await analyze_tender_history(
                        page,
                        conn,
                        active_tender_id=t_data["tender_id"],
                        tender_title=t_data["title"] or "",
                        customer_inn=inn,
                        params=params,
                        source="extended",
                    )
                except Exception as exc:
                    logger.error(
                        f"Ошибка при расширенном анализе тендера "
                        f"{t_data['tender_id']}: {exc}"
                    )

            # Обновляем статус заказчика после завершения
            await update_customer_status(conn, inn, "extended_analyzed")
            await conn.commit()

    logger.info("Этап 3: Расширенный поиск завершён")
