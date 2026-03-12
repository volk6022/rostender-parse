"""Async CRUD-операции для SQLite (aiosqlite)."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import aiosqlite
from loguru import logger

from src.config import DB_PATH, DATA_DIR
from src.db.schema import SCHEMA_SQL


@asynccontextmanager
async def get_connection(
    existing_conn: aiosqlite.Connection | None = None,
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Открыть соединение с БД (async context manager).

    Если передан existing_conn, использует его и не закрывает.
    В противном случае открывает новое соединение и закрывает его по завершении.
    """
    if existing_conn:
        yield existing_conn
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn


async def init_db() -> None:
    """Создать все таблицы (если не существуют)."""
    async with get_connection() as conn:
        await conn.executescript(SCHEMA_SQL)
        await conn.commit()
        logger.info("БД инициализирована: {}", DB_PATH)


# ── Customers ───────────────────────────────────────────────────────────────────


async def upsert_customer(
    conn: aiosqlite.Connection,
    inn: str,
    name: str | None = None,
) -> None:
    """Вставить или обновить заказчика."""
    await upsert_customers_batch(conn, [{"inn": inn, "name": name}])


async def upsert_customers_batch(
    conn: aiosqlite.Connection,
    customers: list[dict[str, Any]],
) -> None:
    """Вставить или обновить список заказчиков (batch)."""
    if not customers:
        return

    values = [(c["inn"], c.get("name")) for c in customers]

    await conn.executemany(
        """
        INSERT INTO customers (inn, name)
        VALUES (?, ?)
        ON CONFLICT(inn) DO UPDATE SET
            name = COALESCE(excluded.name, customers.name)
        """,
        values,
    )


async def update_customer_status(
    conn: aiosqlite.Connection,
    inn: str,
    status: str,
) -> None:
    """Обновить статус заказчика."""
    await conn.execute(
        "UPDATE customers SET status = ?, last_analysis_date = CURRENT_TIMESTAMP WHERE inn = ?",
        (status, inn),
    )


async def get_customers_by_status(
    conn: aiosqlite.Connection,
    status: str,
) -> Sequence[Any]:
    """Получить заказчиков по статусу."""
    cursor = await conn.execute(
        "SELECT * FROM customers WHERE status = ?",
        (status,),
    )
    return list(await cursor.fetchall())


# ── Tenders ─────────────────────────────────────────────────────────────────────


async def upsert_tender(
    conn: aiosqlite.Connection,
    *,
    tender_id: str,
    customer_inn: str,
    url: str | None = None,
    source_urls: str | None = None,
    title: str | None = None,
    price: float | None = None,
    publish_date: str | None = None,
    tender_status: str,
) -> None:
    """Вставить или обновить тендер."""
    await upsert_tenders_batch(
        conn,
        [
            {
                "tender_id": tender_id,
                "customer_inn": customer_inn,
                "url": url,
                "source_urls": source_urls,
                "title": title,
                "price": price,
                "publish_date": publish_date,
                "tender_status": tender_status,
            }
        ],
    )


async def upsert_tenders_batch(
    conn: aiosqlite.Connection,
    tenders: list[dict[str, Any]],
) -> None:
    """Вставить или обновить список тендеров (batch)."""
    if not tenders:
        return

    values = [
        (
            t["tender_id"],
            t["customer_inn"],
            t.get("url"),
            t.get("source_urls"),
            t.get("title"),
            t.get("price"),
            t.get("publish_date"),
            t["tender_status"],
        )
        for t in tenders
    ]

    await conn.executemany(
        """
        INSERT INTO tenders (tender_id, customer_inn, url, source_urls, title, price, publish_date, tender_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tender_id) DO UPDATE SET
            url           = COALESCE(excluded.url, tenders.url),
            source_urls   = COALESCE(excluded.source_urls, tenders.source_urls),
            title         = COALESCE(excluded.title, tenders.title),
            price         = COALESCE(excluded.price, tenders.price),
            publish_date  = COALESCE(excluded.publish_date, tenders.publish_date),
            tender_status = excluded.tender_status
        """,
        values,
    )


async def update_tender_source_urls(
    conn: aiosqlite.Connection,
    tender_id: str,
    source_urls: str,
) -> None:
    """Обновить список внешних ссылок на источники для тендера."""
    await conn.execute(
        "UPDATE tenders SET source_urls = ? WHERE tender_id = ?",
        (source_urls, tender_id),
    )


async def get_tenders_by_customer(
    conn: aiosqlite.Connection,
    customer_inn: str,
    tender_status: str | None = None,
    limit: int | None = None,
) -> Sequence[Any]:
    """Получить тендеры заказчика с опциональной фильтрацией по статусу."""
    query = "SELECT * FROM tenders WHERE customer_inn = ?"
    params: list = [customer_inn]

    if tender_status is not None:
        query += " AND tender_status = ?"
        params.append(tender_status)

    query += " ORDER BY publish_date DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor = await conn.execute(query, params)
    return list(await cursor.fetchall())


async def get_active_tenders(conn: aiosqlite.Connection) -> Sequence[Any]:
    """Получить все активные тендеры."""
    cursor = await conn.execute(
        "SELECT * FROM tenders WHERE tender_status = 'active' ORDER BY price DESC"
    )
    return list(await cursor.fetchall())


# ── Protocol Analysis ───────────────────────────────────────────────────────────


async def upsert_protocol_analysis(
    conn: aiosqlite.Connection,
    *,
    tender_id: str,
    participants_count: int | None = None,
    parse_source: str | None = None,
    parse_status: str,
    doc_path: str | None = None,
    notes: str | None = None,
    tender_protocol_index: int | None = None,
) -> None:
    """Вставить или обновить результат парсинга протокола.

    Args:
        tender_id: ID тендера
        participants_count: Количество участников (None если не определено)
        parse_source: Источник парсинга (html|docx|pdf_text|deduplicated и т.д.)
        parse_status: Статус (success|failed|deduplicated и т.д.)
        doc_path: Путь к скачанному файлу
        notes: Дополнительные заметки
        tender_protocol_index: Индекс протокола (NULL для де-дуплицированного результата, 1+ для отдельных протоколов)
    """
    await conn.execute(
        """
        INSERT INTO protocol_analysis (tender_id, tender_protocol_index, participants_count, parse_source, parse_status, doc_path, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tender_id, tender_protocol_index) DO UPDATE SET
            participants_count = excluded.participants_count,
            parse_source       = excluded.parse_source,
            parse_status       = excluded.parse_status,
            doc_path           = excluded.doc_path,
            notes              = excluded.notes,
            analyzed_at        = CURRENT_TIMESTAMP
        """,
        (
            tender_id,
            tender_protocol_index,
            participants_count,
            parse_source,
            parse_status,
            doc_path,
            notes,
        ),
    )


async def get_protocol_analyses_for_tender(
    conn: aiosqlite.Connection,
    tender_id: str,
) -> Sequence[Any]:
    """Получить все протоколы для конкретного tender_id.

    Возвращает все записи protocol_analysis для данного tender_id
    упорядоченные по tender_protocol_index для последовательного анализа.

    Returns:
        Список словарей с полями: id, tender_id, tender_protocol_index,
        doc_path, parse_status, analyzed_at
    """
    cursor = await conn.execute(
        """
        SELECT id, tender_id, tender_protocol_index, doc_path, parse_status, analyzed_at
        FROM protocol_analysis 
        WHERE tender_id = ?
        ORDER BY tender_protocol_index
        """,
        (tender_id,),
    )
    return list(await cursor.fetchall())


async def get_protocol_analyses_for_customer(
    conn: aiosqlite.Connection,
    customer_inn: str,
) -> Sequence[Any]:
    """Получить результаты анализа протоколов для тендеров заказчика."""
    cursor = await conn.execute(
        """
        SELECT pa.* FROM protocol_analysis pa
        JOIN tenders t ON pa.tender_id = t.tender_id
        WHERE t.customer_inn = ?
        ORDER BY pa.analyzed_at DESC
        """,
        (customer_inn,),
    )
    return list(await cursor.fetchall())


# ── Results ─────────────────────────────────────────────────────────────────────


async def insert_result(
    conn: aiosqlite.Connection,
    *,
    active_tender_id: str,
    customer_inn: str,
    total_historical: int,
    total_analyzed: int,
    total_skipped: int,
    low_competition_count: int,
    competition_ratio: float | None,
    is_interesting: bool,
    source: str = "primary",
) -> None:
    """Записать результат анализа конкуренции."""
    await conn.execute(
        """
        INSERT INTO results (
            active_tender_id, customer_inn,
            total_historical, total_analyzed, total_skipped,
            low_competition_count, competition_ratio,
            is_interesting, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            active_tender_id,
            customer_inn,
            total_historical,
            total_analyzed,
            total_skipped,
            low_competition_count,
            competition_ratio,
            int(is_interesting),
            source,
        ),
    )


async def get_interesting_results(conn: aiosqlite.Connection) -> Sequence[Any]:
    """Получить все интересные результаты с данными тендеров и заказчиков."""
    cursor = await conn.execute(
        """
        SELECT
            r.*,
            t.title   AS tender_title,
            t.url     AS tender_url,
            t.price   AS tender_price,
            c.name    AS customer_name
        FROM results r
        JOIN tenders   t ON r.active_tender_id = t.tender_id
        JOIN customers c ON r.customer_inn     = c.inn
        WHERE r.is_interesting = 1
        ORDER BY r.competition_ratio DESC
        """
    )
    return list(await cursor.fetchall())


async def get_interesting_customers(
    conn: aiosqlite.Connection,
) -> Sequence[Any]:
    """Получить список уникальных ИНН заказчиков с интересными результатами."""
    cursor = await conn.execute(
        """
        SELECT DISTINCT c.inn, c.name
        FROM customers c
        JOIN results r ON c.inn = r.customer_inn
        WHERE r.is_interesting = 1
        """
    )
    return list(await cursor.fetchall())


async def get_customer_metrics(
    conn: aiosqlite.Connection,
    customer_inn: str,
) -> dict[str, Any] | None:
    """Получить метрики последнего успешного анализа для заказчика."""
    cursor = await conn.execute(
        """
        SELECT 
            total_historical, total_analyzed, total_skipped, 
            low_competition_count, competition_ratio
        FROM results 
        WHERE customer_inn = ? 
        ORDER BY created_at DESC 
        LIMIT 1
        """,
        (customer_inn,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def tender_exists(
    conn: aiosqlite.Connection,
    tender_id: str,
) -> bool:
    """Проверить, существует ли тендер в базе."""
    cursor = await conn.execute(
        "SELECT 1 FROM tenders WHERE tender_id = ?",
        (tender_id,),
    )
    row = await cursor.fetchone()
    return row is not None


async def result_exists(
    conn: aiosqlite.Connection,
    active_tender_id: str,
) -> bool:
    """Проверить, существует ли результат для тендера в базе."""
    cursor = await conn.execute(
        "SELECT 1 FROM results WHERE active_tender_id = ?",
        (active_tender_id,),
    )
    row = await cursor.fetchone()
    return row is not None


async def get_latest_protocol_analyses(
    conn: aiosqlite.Connection,
    customer_inn: str,
    tender_ids: list[str],
) -> Sequence[Any]:
    """Получить результаты анализа протоколов только для указанных тендеров."""
    if not tender_ids:
        return []
    placeholders = ", ".join("?" * len(tender_ids))
    cursor = await conn.execute(
        f"""
        SELECT pa.* FROM protocol_analysis pa
        JOIN tenders t ON pa.tender_id = t.tender_id
        WHERE t.customer_inn = ? AND pa.tender_id IN ({placeholders})
        ORDER BY pa.analyzed_at DESC
        """,
        (customer_inn, *tender_ids),
    )
    return list(await cursor.fetchall())


async def save_protocol_analysis_result(
    conn: aiosqlite.Connection,
    *,
    tender_id: str,
    participants_count: int | None,
    parse_source: str,
    parse_status: str,
    doc_path: str | None = None,
    notes: str | None = None,
) -> None:
    """Сохранить итоговый/де-дуплицированный результат для tender_id.

    Де-дуплицированный результат (tender_protocol_index=NULL) перезаписывает
    предыдущие записи для этого tender_id.

    Если результат уже есть с таким же количеством участников — пропускаем
    (для избежания дублей в результатах).
    """
    # Проверяем, есть ли уже результат с таким же количеством
    existing = await conn.execute(
        """
        SELECT id FROM protocol_analysis 
        WHERE tender_id = ? 
          AND (participants_count = ? OR (participants_count IS NULL AND ? IS NULL))
          AND parse_status = 'deduplicated'
        """,
        (tender_id, participants_count, participants_count),
    )
    row = await existing.fetchone()

    if row is not None:
        # Результат уже сохранён — пропускаем
        logger.debug(
            "Результат для tender_id {} уже существует (count={}). Пропускаю.",
            tender_id,
            participants_count,
        )
        return

    await upsert_protocol_analysis(
        conn,
        tender_id=tender_id,
        participants_count=participants_count,
        parse_source=parse_source,
        parse_status=parse_status,
        doc_path=doc_path,
        notes=notes,
        tender_protocol_index=None,  # NULL для де-дуплицированного результата
    )


# ── Reports ──────────────────────────────────────────────────────────────────────


async def get_all_customers(conn: aiosqlite.Connection) -> Sequence[Any]:
    """Получить всех заказчиков с информацией о тендерах."""
    cursor = await conn.execute(
        """
        SELECT
            c.inn,
            c.name,
            c.status,
            c.last_analysis_date,
            COUNT(t.tender_id) AS total_tenders,
            SUM(CASE WHEN t.tender_status = 'active' THEN 1 ELSE 0 END) AS active_tenders,
            SUM(CASE WHEN t.tender_status = 'completed' THEN 1 ELSE 0 END) AS completed_tenders
        FROM customers c
        LEFT JOIN tenders t ON c.inn = t.customer_inn
        GROUP BY c.inn
        ORDER BY c.inn
        """
    )
    return list(await cursor.fetchall())


async def get_all_results(conn: aiosqlite.Connection) -> Sequence[Any]:
    """Получить все результаты с данными тендеров и заказчиков."""
    cursor = await conn.execute(
        """
        SELECT
            r.*,
            t.title   AS tender_title,
            t.url     AS tender_url,
            t.price   AS tender_price,
            c.name    AS customer_name
        FROM results r
        JOIN tenders   t ON r.active_tender_id = t.tender_id
        JOIN customers c ON r.customer_inn     = c.inn
        ORDER BY r.is_interesting DESC, r.competition_ratio DESC
        """
    )
    return list(await cursor.fetchall())


async def get_all_protocol_analyses(conn: aiosqlite.Connection) -> Sequence[Any]:
    """Получить все результаты анализа протоколов с данными тендеров."""
    cursor = await conn.execute(
        """
        SELECT
            pa.*,
            t.title        AS tender_title,
            t.customer_inn AS customer_inn,
            t.tender_status AS tender_status
        FROM protocol_analysis pa
        JOIN tenders t ON pa.tender_id = t.tender_id
        ORDER BY pa.analyzed_at DESC
        """
    )
    return list(await cursor.fetchall())
