"""Async CRUD-операции для SQLite (aiosqlite)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
from loguru import logger

from src.config import DB_PATH, DATA_DIR
from src.db.schema import SCHEMA_SQL


@asynccontextmanager
async def get_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Открыть соединение с БД (async context manager).

    Usage::

        async with get_connection() as conn:
            await conn.execute(...)
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        await conn.close()


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
    await conn.execute(
        """
        INSERT INTO customers (inn, name)
        VALUES (?, ?)
        ON CONFLICT(inn) DO UPDATE SET
            name = COALESCE(excluded.name, customers.name)
        """,
        (inn, name),
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
) -> list[aiosqlite.Row]:
    """Получить заказчиков по статусу."""
    cursor = await conn.execute(
        "SELECT * FROM customers WHERE status = ?",
        (status,),
    )
    return await cursor.fetchall()


# ── Tenders ─────────────────────────────────────────────────────────────────────


async def upsert_tender(
    conn: aiosqlite.Connection,
    *,
    tender_id: str,
    customer_inn: str,
    url: str | None = None,
    eis_url: str | None = None,
    title: str | None = None,
    price: float | None = None,
    publish_date: str | None = None,
    tender_status: str,
) -> None:
    """Вставить или обновить тендер."""
    await conn.execute(
        """
        INSERT INTO tenders (tender_id, customer_inn, url, eis_url, title, price, publish_date, tender_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tender_id) DO UPDATE SET
            url          = COALESCE(excluded.url, tenders.url),
            eis_url      = COALESCE(excluded.eis_url, tenders.eis_url),
            title        = COALESCE(excluded.title, tenders.title),
            price        = COALESCE(excluded.price, tenders.price),
            publish_date = COALESCE(excluded.publish_date, tenders.publish_date),
            tender_status = excluded.tender_status
        """,
        (
            tender_id,
            customer_inn,
            url,
            eis_url,
            title,
            price,
            publish_date,
            tender_status,
        ),
    )


async def get_tenders_by_customer(
    conn: aiosqlite.Connection,
    customer_inn: str,
    tender_status: str | None = None,
    limit: int | None = None,
) -> list[aiosqlite.Row]:
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
    return await cursor.fetchall()


async def get_active_tenders(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    """Получить все активные тендеры."""
    cursor = await conn.execute(
        "SELECT * FROM tenders WHERE tender_status = 'active' ORDER BY price DESC"
    )
    return await cursor.fetchall()


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
) -> None:
    """Вставить или обновить результат парсинга протокола."""
    await conn.execute(
        """
        INSERT INTO protocol_analysis (tender_id, participants_count, parse_source, parse_status, doc_path, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(tender_id) DO UPDATE SET
            participants_count = excluded.participants_count,
            parse_source       = excluded.parse_source,
            parse_status       = excluded.parse_status,
            doc_path           = excluded.doc_path,
            notes              = excluded.notes,
            analyzed_at        = CURRENT_TIMESTAMP
        """,
        (tender_id, participants_count, parse_source, parse_status, doc_path, notes),
    )


async def get_protocol_analyses_for_customer(
    conn: aiosqlite.Connection,
    customer_inn: str,
) -> list[aiosqlite.Row]:
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
    return await cursor.fetchall()


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


async def get_interesting_results(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
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
    return await cursor.fetchall()
