"""Tests for db/repository.py."""

from __future__ import annotations

import pytest

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
