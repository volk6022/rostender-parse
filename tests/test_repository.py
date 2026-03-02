"""Tests for db/repository.py."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import aiosqlite

from src.db.repository import (
    get_customers_by_status,
    get_tenders_by_customer,
    get_protocol_analyses_for_customer,
    insert_result,
    tender_exists,
    result_exists,
    update_customer_status,
    upsert_customer,
    upsert_tender,
    upsert_protocol_analysis,
    get_interesting_results,
    get_interesting_customers,
    get_all_customers,
    get_all_results,
    get_all_protocol_analyses,
    get_latest_protocol_analyses,
)


class TestCustomers:
    """Tests for customer operations."""

    @pytest.mark.asyncio
    async def test_upsert_customer(self, test_db: aiosqlite.Connection) -> None:
        """Тест вставки и обновления заказчика."""
        await upsert_customer(test_db, inn="1234567890", name="Тестовая компания")

        customers = await get_customers_by_status(test_db, "new")
        assert len(customers) == 1
        assert customers[0]["inn"] == "1234567890"
        assert customers[0]["name"] == "Тестовая компания"

    @pytest.mark.asyncio
    async def test_upsert_customer_update(self, test_db: aiosqlite.Connection) -> None:
        """Тест обновления заказчика."""
        await upsert_customer(test_db, inn="1234567890", name="Компания 1")
        await upsert_customer(test_db, inn="1234567890", name="Компания 2")

        customers = await get_customers_by_status(test_db, "new")
        assert len(customers) == 1
        assert customers[0]["name"] == "Компания 2"

    @pytest.mark.asyncio
    async def test_update_customer_status(self, test_db: aiosqlite.Connection) -> None:
        """Тест обновления статуса заказчика."""
        await upsert_customer(test_db, inn="1234567890", name="Тест")
        await update_customer_status(test_db, "1234567890", "processing")

        customers = await get_customers_by_status(test_db, "processing")
        assert len(customers) == 1
        assert customers[0]["inn"] == "1234567890"


class TestTenders:
    """Tests for tender operations."""

    @pytest.mark.asyncio
    async def test_upsert_tender(self, test_db: aiosqlite.Connection) -> None:
        """Тест вставки тендера."""
        await upsert_customer(test_db, inn="1234567890", name="Заказчик")
        await upsert_tender(
            test_db,
            tender_id="tender_001",
            customer_inn="1234567890",
            url="https://rostender.info/tender/001",
            title="Поставка оборудования",
            price=30_000_000,
            tender_status="active",
        )

        tenders = await get_tenders_by_customer(
            test_db, "1234567890", tender_status="active"
        )
        assert len(tenders) == 1
        assert tenders[0]["tender_id"] == "tender_001"
        assert tenders[0]["title"] == "Поставка оборудования"
        assert tenders[0]["price"] == 30_000_000

    @pytest.mark.asyncio
    async def test_tender_exists(self, test_db: aiosqlite.Connection) -> None:
        """Тест проверки существования тендера."""
        await upsert_customer(test_db, inn="1234567890")
        await upsert_tender(
            test_db,
            tender_id="tender_001",
            customer_inn="1234567890",
            tender_status="active",
        )

        exists = await tender_exists(test_db, "tender_001")
        assert exists is True

        not_exists = await tender_exists(test_db, "tender_nonexistent")
        assert not_exists is False


class TestProtocolAnalysis:
    """Tests for protocol analysis operations."""

    @pytest.mark.asyncio
    async def test_upsert_protocol_analysis(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Тест вставки результата парсинга протокола."""
        await upsert_customer(test_db, inn="1234567890")
        await upsert_tender(
            test_db,
            tender_id="tender_001",
            customer_inn="1234567890",
            tender_status="completed",
        )
        await upsert_protocol_analysis(
            test_db,
            tender_id="tender_001",
            participants_count=3,
            parse_source="html",
            parse_status="success",
        )

        analyses = await get_protocol_analyses_for_customer(test_db, "1234567890")
        assert len(analyses) == 1
        assert analyses[0]["participants_count"] == 3
        assert analyses[0]["parse_status"] == "success"


class TestResults:
    """Tests for result operations."""

    @pytest.mark.asyncio
    async def test_insert_result(self, test_db: aiosqlite.Connection) -> None:
        """Тест вставки результата анализа."""
        await upsert_customer(test_db, inn="1234567890")
        await upsert_tender(
            test_db,
            tender_id="tender_active",
            customer_inn="1234567890",
            tender_status="active",
        )
        await insert_result(
            test_db,
            active_tender_id="tender_active",
            customer_inn="1234567890",
            total_historical=5,
            total_analyzed=4,
            total_skipped=1,
            low_competition_count=3,
            competition_ratio=0.75,
            is_interesting=True,
        )

        results = await get_interesting_results(test_db)
        assert len(results) == 1
        assert results[0]["is_interesting"] == 1
        assert results[0]["competition_ratio"] == 0.75

    @pytest.mark.asyncio
    async def test_result_exists(self, test_db: aiosqlite.Connection) -> None:
        """Тест проверки существования результата."""
        await upsert_customer(test_db, inn="1234567890")
        await upsert_tender(
            test_db,
            tender_id="tender_active",
            customer_inn="1234567890",
            tender_status="active",
        )
        await insert_result(
            test_db,
            active_tender_id="tender_active",
            customer_inn="1234567890",
            total_historical=5,
            total_analyzed=5,
            total_skipped=0,
            low_competition_count=4,
            competition_ratio=0.8,
            is_interesting=True,
        )

        exists = await result_exists(test_db, "tender_active")
        assert exists is True

        not_exists = await result_exists(test_db, "nonexistent_tender")
        assert not_exists is False


class TestGetLatestProtocolAnalyses:
    """Tests for get_latest_protocol_analyses."""

    @pytest.mark.asyncio
    async def test_get_latest_by_tender_ids(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Тест получения анализов только для указанных тендеров."""
        await upsert_customer(test_db, inn="1234567890")

        for i in range(5):
            await upsert_tender(
                test_db,
                tender_id=f"tender_{i}",
                customer_inn="1234567890",
                tender_status="completed",
            )
            await upsert_protocol_analysis(
                test_db,
                tender_id=f"tender_{i}",
                participants_count=i + 1,
                parse_source="html",
                parse_status="success",
            )

        analyses = await get_latest_protocol_analyses(
            test_db,
            customer_inn="1234567890",
            tender_ids=["tender_0", "tender_2", "tender_4"],
        )

        assert len(analyses) == 3
        tender_ids = {row["tender_id"] for row in analyses}
        assert tender_ids == {"tender_0", "tender_2", "tender_4"}

    @pytest.mark.asyncio
    async def test_empty_tender_ids(self, test_db: aiosqlite.Connection) -> None:
        """Тест с пустым списком tender_ids."""
        await upsert_customer(test_db, inn="1234567890")

        analyses = await get_latest_protocol_analyses(
            test_db,
            customer_inn="1234567890",
            tender_ids=[],
        )

        assert len(analyses) == 0


class TestReports:
    """Tests for report queries."""

    @pytest.mark.asyncio
    async def test_get_all_customers(self, test_db: aiosqlite.Connection) -> None:
        """Тест получения всех заказчиков с статистикой."""
        await upsert_customer(test_db, inn="1234567890", name="Компания 1")
        await upsert_customer(test_db, inn="1234567891", name="Компания 2")

        await upsert_tender(
            test_db,
            tender_id="t1",
            customer_inn="1234567890",
            tender_status="active",
        )
        await upsert_tender(
            test_db,
            tender_id="t2",
            customer_inn="1234567890",
            tender_status="completed",
        )

        customers = await get_all_customers(test_db)

        assert len(customers) == 2
        c1 = next(c for c in customers if c["inn"] == "1234567890")
        assert c1["total_tenders"] == 2
        assert c1["active_tenders"] == 1
        assert c1["completed_tenders"] == 1

    @pytest.mark.asyncio
    async def test_get_all_customers_no_tenders(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Customer with no tenders has zero counts."""
        await upsert_customer(test_db, inn="0000000000", name="Empty")

        customers = await get_all_customers(test_db)
        assert len(customers) == 1
        assert customers[0]["total_tenders"] == 0
        assert customers[0]["active_tenders"] == 0
        assert customers[0]["completed_tenders"] == 0


class TestGetActiveTenders:
    """Tests for get_active_tenders."""

    @pytest.mark.asyncio
    async def test_returns_active_tenders_only(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Returns only tenders with status 'active'."""
        await upsert_customer(test_db, inn="1234567890")
        await upsert_tender(
            test_db,
            tender_id="t_active",
            customer_inn="1234567890",
            price=10_000_000,
            tender_status="active",
        )
        await upsert_tender(
            test_db,
            tender_id="t_completed",
            customer_inn="1234567890",
            price=20_000_000,
            tender_status="completed",
        )

        from src.db.repository import get_active_tenders

        result = await get_active_tenders(test_db)

        assert len(result) == 1
        assert result[0]["tender_id"] == "t_active"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_active(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Returns empty list when no active tenders exist."""
        await upsert_customer(test_db, inn="1234567890")
        await upsert_tender(
            test_db,
            tender_id="t_completed",
            customer_inn="1234567890",
            tender_status="completed",
        )

        from src.db.repository import get_active_tenders

        result = await get_active_tenders(test_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_ordered_by_price_desc(self, test_db: aiosqlite.Connection) -> None:
        """Active tenders are ordered by price descending."""
        await upsert_customer(test_db, inn="1234567890")
        await upsert_tender(
            test_db,
            tender_id="t_cheap",
            customer_inn="1234567890",
            price=1_000_000,
            tender_status="active",
        )
        await upsert_tender(
            test_db,
            tender_id="t_expensive",
            customer_inn="1234567890",
            price=50_000_000,
            tender_status="active",
        )

        from src.db.repository import get_active_tenders

        result = await get_active_tenders(test_db)

        assert len(result) == 2
        assert result[0]["tender_id"] == "t_expensive"
        assert result[1]["tender_id"] == "t_cheap"


class TestGetInterestingCustomers:
    """Tests for get_interesting_customers."""

    @pytest.mark.asyncio
    async def test_returns_customers_with_interesting_results(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Returns customers that have at least one interesting result."""
        await upsert_customer(test_db, inn="1111111111", name="Interesting Co")
        await upsert_tender(
            test_db,
            tender_id="t1",
            customer_inn="1111111111",
            tender_status="active",
        )
        await insert_result(
            test_db,
            active_tender_id="t1",
            customer_inn="1111111111",
            total_historical=5,
            total_analyzed=5,
            total_skipped=0,
            low_competition_count=5,
            competition_ratio=1.0,
            is_interesting=True,
        )

        result = await get_interesting_customers(test_db)

        assert len(result) == 1
        assert result[0]["inn"] == "1111111111"
        assert result[0]["name"] == "Interesting Co"

    @pytest.mark.asyncio
    async def test_excludes_non_interesting_customers(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Does not return customers with only non-interesting results."""
        await upsert_customer(test_db, inn="2222222222", name="Boring Co")
        await upsert_tender(
            test_db,
            tender_id="t2",
            customer_inn="2222222222",
            tender_status="active",
        )
        await insert_result(
            test_db,
            active_tender_id="t2",
            customer_inn="2222222222",
            total_historical=5,
            total_analyzed=5,
            total_skipped=0,
            low_competition_count=0,
            competition_ratio=0.0,
            is_interesting=False,
        )

        result = await get_interesting_customers(test_db)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_distinct_customers(self, test_db: aiosqlite.Connection) -> None:
        """Returns each customer only once even with multiple interesting results."""
        await upsert_customer(test_db, inn="3333333333", name="Multi Co")
        await upsert_tender(
            test_db,
            tender_id="t3a",
            customer_inn="3333333333",
            tender_status="active",
        )
        await upsert_tender(
            test_db,
            tender_id="t3b",
            customer_inn="3333333333",
            tender_status="active",
        )
        await insert_result(
            test_db,
            active_tender_id="t3a",
            customer_inn="3333333333",
            total_historical=3,
            total_analyzed=3,
            total_skipped=0,
            low_competition_count=3,
            competition_ratio=1.0,
            is_interesting=True,
        )
        await insert_result(
            test_db,
            active_tender_id="t3b",
            customer_inn="3333333333",
            total_historical=2,
            total_analyzed=2,
            total_skipped=0,
            low_competition_count=2,
            competition_ratio=1.0,
            is_interesting=True,
        )

        result = await get_interesting_customers(test_db)

        assert len(result) == 1


class TestGetAllResults:
    """Tests for get_all_results."""

    @pytest.mark.asyncio
    async def test_returns_results_with_joined_data(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Returns results joined with tender and customer data."""
        await upsert_customer(test_db, inn="1234567890", name="Test Co")
        await upsert_tender(
            test_db,
            tender_id="t1",
            customer_inn="1234567890",
            title="Test Tender",
            url="https://example.com/t1",
            price=10_000_000,
            tender_status="active",
        )
        await insert_result(
            test_db,
            active_tender_id="t1",
            customer_inn="1234567890",
            total_historical=3,
            total_analyzed=3,
            total_skipped=0,
            low_competition_count=2,
            competition_ratio=0.67,
            is_interesting=False,
        )

        result = await get_all_results(test_db)

        assert len(result) == 1
        row = result[0]
        assert row["tender_title"] == "Test Tender"
        assert row["tender_url"] == "https://example.com/t1"
        assert row["tender_price"] == 10_000_000
        assert row["customer_name"] == "Test Co"

    @pytest.mark.asyncio
    async def test_ordered_by_interesting_then_ratio(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Results ordered by is_interesting DESC, competition_ratio DESC."""
        await upsert_customer(test_db, inn="1234567890", name="Co")
        await upsert_tender(
            test_db,
            tender_id="t_boring",
            customer_inn="1234567890",
            tender_status="active",
        )
        await upsert_tender(
            test_db,
            tender_id="t_interesting",
            customer_inn="1234567890",
            tender_status="active",
        )
        await insert_result(
            test_db,
            active_tender_id="t_boring",
            customer_inn="1234567890",
            total_historical=5,
            total_analyzed=5,
            total_skipped=0,
            low_competition_count=1,
            competition_ratio=0.2,
            is_interesting=False,
        )
        await insert_result(
            test_db,
            active_tender_id="t_interesting",
            customer_inn="1234567890",
            total_historical=5,
            total_analyzed=5,
            total_skipped=0,
            low_competition_count=5,
            competition_ratio=1.0,
            is_interesting=True,
        )

        result = await get_all_results(test_db)

        assert len(result) == 2
        # Interesting first
        assert result[0]["active_tender_id"] == "t_interesting"
        assert result[1]["active_tender_id"] == "t_boring"

    @pytest.mark.asyncio
    async def test_empty_results(self, test_db: aiosqlite.Connection) -> None:
        """Returns empty list when no results exist."""
        result = await get_all_results(test_db)
        assert result == []


class TestGetAllProtocolAnalyses:
    """Tests for get_all_protocol_analyses."""

    @pytest.mark.asyncio
    async def test_returns_analyses_with_tender_data(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Returns protocol analyses joined with tender data."""
        await upsert_customer(test_db, inn="1234567890")
        await upsert_tender(
            test_db,
            tender_id="t1",
            customer_inn="1234567890",
            title="Поставка серверов",
            tender_status="completed",
        )
        await upsert_protocol_analysis(
            test_db,
            tender_id="t1",
            participants_count=3,
            parse_source="html",
            parse_status="success",
            doc_path="/downloads/t1.pdf",
            notes="OK",
        )

        result = await get_all_protocol_analyses(test_db)

        assert len(result) == 1
        row = result[0]
        assert row["tender_title"] == "Поставка серверов"
        assert row["customer_inn"] == "1234567890"
        assert row["tender_status"] == "completed"
        assert row["participants_count"] == 3
        assert row["parse_source"] == "html"
        assert row["doc_path"] == "/downloads/t1.pdf"

    @pytest.mark.asyncio
    async def test_multiple_analyses_ordered_by_date(
        self, test_db: aiosqlite.Connection
    ) -> None:
        """Multiple analyses are returned ordered by analyzed_at DESC."""
        await upsert_customer(test_db, inn="1234567890")
        for i in range(3):
            await upsert_tender(
                test_db,
                tender_id=f"t{i}",
                customer_inn="1234567890",
                tender_status="completed",
            )
            await upsert_protocol_analysis(
                test_db,
                tender_id=f"t{i}",
                participants_count=i + 1,
                parse_status="success",
            )

        result = await get_all_protocol_analyses(test_db)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_empty_analyses(self, test_db: aiosqlite.Connection) -> None:
        """Returns empty list when no analyses exist."""
        result = await get_all_protocol_analyses(test_db)
        assert result == []


class TestGetConnection:
    """Tests for get_connection async context manager."""

    @pytest.mark.asyncio
    async def test_yields_connection_and_closes(self, tmp_path: Path) -> None:
        """get_connection yields a working connection and closes it."""
        from unittest.mock import patch

        db_path = tmp_path / "data" / "test.db"

        with (
            patch("src.db.repository.DB_PATH", db_path),
            patch("src.db.repository.DATA_DIR", tmp_path / "data"),
        ):
            from src.db.repository import get_connection

            async with get_connection() as conn:
                # Connection should be usable
                await conn.execute("SELECT 1")
                assert conn.row_factory is not None

        # Directory was created
        assert (tmp_path / "data").exists()

    @pytest.mark.asyncio
    async def test_sets_wal_and_foreign_keys(self, tmp_path: Path) -> None:
        """get_connection enables WAL journal mode and foreign keys."""
        from unittest.mock import patch

        db_path = tmp_path / "data" / "test.db"

        with (
            patch("src.db.repository.DB_PATH", db_path),
            patch("src.db.repository.DATA_DIR", tmp_path / "data"),
        ):
            from src.db.repository import get_connection

            async with get_connection() as conn:
                cursor = await conn.execute("PRAGMA journal_mode")
                row = await cursor.fetchone()
                assert row is not None
                mode = row[0]
                assert mode == "wal"

                cursor = await conn.execute("PRAGMA foreign_keys")
                row = await cursor.fetchone()
                assert row is not None
                fk = row[0]
                assert fk == 1


class TestInitDb:
    """Tests for init_db."""

    @pytest.mark.asyncio
    async def test_creates_all_tables(self, tmp_path: Path) -> None:
        """init_db creates all required tables."""
        from unittest.mock import patch

        db_path = tmp_path / "data" / "test.db"

        with (
            patch("src.db.repository.DB_PATH", db_path),
            patch("src.db.repository.DATA_DIR", tmp_path / "data"),
        ):
            from src.db.repository import get_connection, init_db

            await init_db()

            async with get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = [row[0] for row in await cursor.fetchall()]

        assert "customers" in tables
        assert "tenders" in tables
        assert "protocol_analysis" in tables
        assert "results" in tables

    @pytest.mark.asyncio
    async def test_idempotent(self, tmp_path: Path) -> None:
        """init_db can be called multiple times without error."""
        from unittest.mock import patch

        db_path = tmp_path / "data" / "test.db"

        with (
            patch("src.db.repository.DB_PATH", db_path),
            patch("src.db.repository.DATA_DIR", tmp_path / "data"),
        ):
            from src.db.repository import init_db

            await init_db()
            await init_db()  # Should not raise
