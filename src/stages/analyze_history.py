"""Этап 2: Поиск завершённых тендеров по ИНН, парсинг протоколов, расчёт метрик."""

from __future__ import annotations

from loguru import logger
from playwright.async_api import Page

from src.db.repository import (
    get_connection,
    get_customers_by_status,
    get_tenders_by_customer,
    update_customer_status,
)
from src.scraper.auth import ensure_logged_in
from src.stages._history_helpers import analyze_tender_history
from src.stages.params import PipelineParams

# Проверять сессию каждые N заказчиков
_SESSION_CHECK_INTERVAL = 10
# Максимум последовательных ошибок до принудительной проверки сессии
_MAX_CONSECUTIVE_ERRORS = 3


async def _recover_page(page: Page) -> None:
    """Сбросить страницу в чистое состояние после ошибки."""
    try:
        await page.goto("about:blank", timeout=5_000)
    except Exception:
        pass


async def run_analyze_history(page: Page, params: PipelineParams) -> None:
    """Этап 2: Анализ истории заказчиков.

    Выполняет:
      2.1  Получение заказчиков со статусом ``new``
      2.2  Для каждого заказчика — поиск завершённых тендеров
      2.3  Парсинг протоколов (PDF / DOCX / HTML)
      2.4  Расчёт метрик конкуренции
      2.5  Сохранение результатов

    Зависимости данных: требует заказчиков со статусом ``new`` в БД (Этап 1).
    """
    logger.info("Этап 2: Поиск завершённых тендеров по ИНН заказчиков")

    async with get_connection() as conn:
        new_customers = await get_customers_by_status(conn, "new")
    logger.info(f"Заказчиков со статусом 'new': {len(new_customers)}")

    if not new_customers:
        logger.info("Нет заказчиков для анализа (статус 'new')")
        return

    consecutive_errors = 0

    async with get_connection() as conn:
        for idx, customer in enumerate(new_customers):
            inn = customer["inn"]
            name = customer["name"] or inn
            logger.info(
                f"Обработка заказчика {name} (ИНН {inn})... "
                f"[{idx + 1}/{len(new_customers)}]"
            )

            # Периодическая проверка сессии
            if idx > 0 and idx % _SESSION_CHECK_INTERVAL == 0:
                logger.debug(
                    "Плановая проверка сессии (каждые {} заказчиков)...",
                    _SESSION_CHECK_INTERVAL,
                )
                await ensure_logged_in(page)

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
                    consecutive_errors = 0
                    continue

                # 2.3 Для каждого активного тендера — анализ истории
                for active_tender in active_tenders_list:
                    tender_id = active_tender["tender_id"]
                    tender_title = active_tender["title"] or ""

                    logger.info(f"Анализ тендера {tender_id}: '{tender_title[:50]}...'")

                    await analyze_tender_history(
                        page,
                        conn,
                        active_tender_id=tender_id,
                        tender_title=tender_title,
                        customer_inn=inn,
                        params=params,
                        source="primary",
                    )

                await update_customer_status(conn, inn, "analyzed")
                await conn.commit()
                consecutive_errors = 0
                logger.success(f"Заказчик {inn}: анализ завершён")

            except Exception as exc:
                consecutive_errors += 1
                logger.error(f"Ошибка при обработке ИНН {inn}: {exc}")
                await update_customer_status(conn, inn, "error")
                await conn.commit()

                # Восстанавливаем страницу после ошибки
                await _recover_page(page)

                # Если подряд несколько ошибок — возможно, сессия протухла
                if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                    logger.warning(
                        "Подряд {} ошибок — проверяем сессию и переавторизуемся...",
                        consecutive_errors,
                    )
                    await ensure_logged_in(page)
                    consecutive_errors = 0

    logger.info("Этап 2: завершён")
