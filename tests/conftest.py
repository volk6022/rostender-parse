"""Pytest fixtures for rostender-parse tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncGenerator, Iterator
from unittest.mock import MagicMock

import aiosqlite
import pytest

from src.config import DATA_DIR, DB_PATH


class MockRow:
    """Mock for aiosqlite.Row that supports dict-like access."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def keys(self) -> list[str]:
        return list(self._data.keys())


@pytest.fixture
def mock_row() -> type[MockRow]:
    """Создаёт мок aiosqlite.Row для тестирования."""
    return MockRow


@pytest.fixture
def sample_analyses_success() -> list[dict[str, Any]]:
    """Пример успешно проанализированных протоколов (все success)."""
    return [
        {"tender_id": "t1", "parse_status": "success", "participants_count": 1},
        {"tender_id": "t2", "parse_status": "success", "participants_count": 2},
        {"tender_id": "t3", "parse_status": "success", "participants_count": 1},
        {"tender_id": "t4", "parse_status": "success", "participants_count": 3},
        {"tender_id": "t5", "parse_status": "success", "participants_count": 2},
    ]


@pytest.fixture
def sample_analyses_mixed() -> list[dict[str, Any]]:
    """Пример смешанных результатов анализа (success + skipped/failed)."""
    return [
        {"tender_id": "t1", "parse_status": "success", "participants_count": 1},
        {"tender_id": "t2", "parse_status": "success", "participants_count": 2},
        {"tender_id": "t3", "parse_status": "failed", "participants_count": None},
        {"tender_id": "t4", "parse_status": "skipped_scan", "participants_count": None},
        {"tender_id": "t5", "parse_status": "success", "participants_count": 1},
    ]


@pytest.fixture
def sample_analyses_empty() -> list[dict[str, Any]]:
    """Пустой список анализов."""
    return []


@pytest.fixture
def sample_protocol_texts() -> dict[str, str]:
    """Примеры текстов протоколов для тестирования парсеров."""
    return {
        "direct_count": """
        Протокол итогов
        Количество поданных заявок: 5
        Дата подведения итогов: 15.01.2026
        """,
        "submitted": """
        Протокол рассмотрения заявок
        Подано 3 заявки на участие в аукционе
        Все заявки допущены к участию
        """,
        "participants_count": """
        Итоговый протокол
        Количество участников: 2
        Победитель: ООО "Ромашка"
        """,
        "admitted": """
        Протокол
        Допущено 4 участника к участию в аукционе
        """,
        "single": """
        Протокол
        Подана единственная заявка
        """,
        "zero": """
        Протокол
        Заявок не поступило
        Тендер признан несостоявшимся
        """,
        "numbered_apps": """
        Заявка №1 ООО "Первый"
        Заявка №2 ООО "Второй"
        Заявка №3 ООО "Третий"
        """,
        "numbered_orgs": """
        1) ООО "Ромашка"
        2) АО "Василёк"
        3) ИП Петров П.П.
        """,
        "inn_count": """
        ИНН заказчика: 1234567890
        ИНН участника 1: 1234567891
        ИНН участника 2: 1234567892
        ИНН участника 3: 1234567893
        """,
        "void_tender": """
        Протокол
        Тендер признан несостоявшимся
        """,
    }


@pytest.fixture
async def test_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Создаёт временную in-memory БД для тестирования."""
    test_db_path = Path(":memory:")
    conn = await aiosqlite.connect(str(test_db_path))
    conn.row_factory = aiosqlite.Row

    schema = """
    CREATE TABLE IF NOT EXISTS customers (
        inn TEXT PRIMARY KEY,
        name TEXT,
        status TEXT DEFAULT 'new',
        last_analysis_date DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tenders (
        tender_id TEXT PRIMARY KEY,
        customer_inn TEXT NOT NULL,
        url TEXT,
        source_urls TEXT,
        title TEXT,
        price REAL,
        publish_date DATETIME,
        tender_status TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(customer_inn) REFERENCES customers(inn)
    );


    CREATE TABLE IF NOT EXISTS protocol_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tender_id TEXT NOT NULL UNIQUE,
        participants_count INTEGER,
        parse_source TEXT,
        parse_status TEXT NOT NULL,
        doc_path TEXT,
        notes TEXT,
        analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(tender_id) REFERENCES tenders(tender_id)
    );

    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        active_tender_id TEXT NOT NULL,
        customer_inn TEXT NOT NULL,
        total_historical INTEGER,
        total_analyzed INTEGER,
        total_skipped INTEGER,
        low_competition_count INTEGER,
        competition_ratio REAL,
        is_interesting BOOLEAN DEFAULT 0,
        source TEXT DEFAULT 'primary',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(active_tender_id) REFERENCES tenders(tender_id),
        FOREIGN KEY(customer_inn) REFERENCES customers(inn)
    );
    """
    await conn.executescript(schema)
    await conn.commit()

    yield conn

    await conn.close()
