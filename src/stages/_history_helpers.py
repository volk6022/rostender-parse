"""Общие хелперы для анализа исторических тендеров (используются Этапами 2 и 3)."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite
from loguru import logger
from playwright.async_api import Page

from src.analyzer.competition import CompetitionMetrics, calculate_metrics, log_metrics
from src.db.repository import (
    get_latest_protocol_analyses,
    insert_result,
    result_exists,
    upsert_tender,
)
from src.parser.html_protocol import analyze_tender_protocol
from src.scraper.historical_search import (
    extract_keywords_from_title,
    search_historical_tenders,
)
from src.stages.params import PipelineParams


@dataclass
class HistoryAnalysisResult:
    """Результат анализа истории для одного активного тендера."""

    historical_count: int
    success_count: int
    failed_count: int
    metrics: CompetitionMetrics | None
    saved: bool


async def analyze_tender_history(
    page: Page,
    conn: aiosqlite.Connection,
    *,
    active_tender_id: str,
    tender_title: str,
    customer_inn: str,
    params: PipelineParams,
    source: str = "primary",
) -> HistoryAnalysisResult:
    """Выполнить полный цикл анализа истории для одного активного тендера.

    Шаги:
      1. Извлечь ключевые слова из заголовка тендера
      2. Найти завершённые тендеры того же заказчика
      3. Сохранить их в БД
      4. Распарсить протоколы
      5. Рассчитать метрики конкуренции
      6. Сохранить результат (если ещё не существует)

    Args:
        page: Playwright-страница (авторизованная).
        conn: Открытое соединение с БД.
        active_tender_id: ID активного тендера, для которого ищем историю.
        tender_title: Заголовок активного тендера (для извлечения ключевых слов).
        customer_inn: ИНН заказчика.
        params: Параметры pipeline.
        source: Источник результата (``"primary"`` или ``"extended"``).

    Returns:
        :class:`HistoryAnalysisResult` с агрегированной статистикой.
    """
    title = tender_title or ""

    # 1. Извлекаем ключевые слова из заголовка
    custom_kw = extract_keywords_from_title(title)
    if custom_kw:
        logger.debug(f"Ключевые слова для поиска: {custom_kw[:3]}...")

    # 2. Поиск завершённых тендеров
    historical = await search_historical_tenders(
        page,
        customer_inn,
        limit=params.history_limit,
        custom_keywords=custom_kw,
        min_price=params.min_price_historical,
    )

    if not historical:
        logger.info(f"Исторические тендеры не найдены для {active_tender_id}")
        return HistoryAnalysisResult(
            historical_count=0,
            success_count=0,
            failed_count=0,
            metrics=None,
            saved=False,
        )

    logger.info(
        f"Найдено {len(historical)} завершённых тендеров для {active_tender_id}"
    )

    # 3. Сохраняем завершённые тендеры в БД (Batch)
    from src.db.repository import upsert_tenders_batch

    tenders_to_batch = [
        {
            "tender_id": t_data["tender_id"],
            "customer_inn": customer_inn,
            "url": t_data["url"],
            "title": t_data["title"],
            "price": t_data["price"],
            "tender_status": "completed",
        }
        for t_data in historical
    ]
    await upsert_tenders_batch(conn, tenders_to_batch)
    await conn.commit()

    historical_ids = [t["tender_id"] for t in tenders_to_batch]

    # 4. Парсинг протоколов
    success_count = 0
    failed_count = 0

    for t_data in historical:
        try:
            result = await analyze_tender_protocol(
                page=page,
                tender_id=t_data["tender_id"],
                tender_url=t_data["url"],
                customer_inn=customer_inn,
                conn=conn,
            )
            if result.parse_status == "success":
                success_count += 1
            else:
                failed_count += 1
        except Exception as proto_exc:
            logger.error(
                f"Ошибка парсинга протокола тендера {t_data['tender_id']}: {proto_exc}"
            )
            failed_count += 1

    # 5. Расчёт метрик
    if historical_ids:
        analyses = await get_latest_protocol_analyses(
            conn, customer_inn, historical_ids
        )
    else:
        analyses = []

    metrics = calculate_metrics(analyses)
    log_metrics(customer_inn, metrics)

    # 6. Сохраняем результат (если ещё нет)
    saved = False
    if await result_exists(conn, active_tender_id):
        logger.debug(f"Результат для тендера {active_tender_id} уже существует")
    elif metrics.is_determinable:
        await insert_result(
            conn,
            active_tender_id=active_tender_id,
            customer_inn=customer_inn,
            total_historical=metrics.total_historical,
            total_analyzed=metrics.total_analyzed,
            total_skipped=metrics.total_skipped,
            low_competition_count=metrics.low_competition_count,
            competition_ratio=metrics.competition_ratio,
            is_interesting=metrics.is_interesting,
            source=source,
        )
        await conn.commit()
        saved = True
        logger.success(
            f"Результат для тендера {active_tender_id} "
            f"(source={source}): is_interesting={metrics.is_interesting}"
        )

    return HistoryAnalysisResult(
        historical_count=len(historical),
        success_count=success_count,
        failed_count=failed_count,
        metrics=metrics,
        saved=saved,
    )
