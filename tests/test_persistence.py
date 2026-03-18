import pytest
import aiosqlite
from src.utils.session import generate_session_id


@pytest.mark.asyncio
async def test_session_status_persistence(test_db: aiosqlite.Connection):
    """Verify RunSession status updates."""
    session_id = generate_session_id()

    # 1. Create session
    await test_db.execute(
        "INSERT INTO run_sessions (session_id, status) VALUES (?, ?)",
        (session_id, "running"),
    )
    await test_db.commit()

    # 2. Update status
    await test_db.execute(
        "UPDATE run_sessions SET status = ?, end_time = CURRENT_TIMESTAMP WHERE session_id = ?",
        ("success", session_id),
    )
    await test_db.commit()

    # 3. Verify
    cursor = await test_db.execute(
        "SELECT status FROM run_sessions WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    assert row["status"] == "success"
