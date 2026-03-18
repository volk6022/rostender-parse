import pytest
import aiosqlite
from src.db.repository import upsert_customer, upsert_tender
from src.db.schema import SCHEMA_SQL


@pytest.mark.asyncio
async def test_data_archival_on_startup(test_db: aiosqlite.Connection):
    """
    Verify that existing data is moved to archive tables.
    Note: This test will need to be updated once archive_old_data is implemented.
    For now, we just verify the schema and initial state.
    """
    # 1. Setup initial data
    await upsert_customer(test_db, inn="1234567890", name="Old Customer")
    await upsert_tender(
        test_db,
        tender_id="old_tender",
        customer_inn="1234567890",
        tender_status="active",
    )

    # Verify data is in active tables
    cursor = await test_db.execute("SELECT COUNT(*) FROM customers")
    assert (await cursor.fetchone())[0] == 1

    # 2. Simulate archival (T003 logic)
    # This is what archive_old_data will do
    await test_db.execute(
        "INSERT INTO customers_archive (inn, name, created_at) SELECT inn, name, created_at FROM customers"
    )
    await test_db.execute("DELETE FROM customers")

    # 3. Verify archival
    cursor = await test_db.execute("SELECT COUNT(*) FROM customers")
    assert (await cursor.fetchone())[0] == 0

    cursor = await test_db.execute("SELECT COUNT(*) FROM customers_archive")
    assert (await cursor.fetchone())[0] == 1
