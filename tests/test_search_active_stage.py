"""Тесты для src/stages/search_active.py — Этап 1: оркестрация."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.stages.search_active import run_search_active


def _make_params(**overrides):
    """Создаёт мок PipelineParams."""
    defaults = dict(
        keywords="строительство",
        min_price_active=500_000,
        date_from="01.01.2024",
        date_to="31.12.2024",
    )
    defaults.update(overrides)
    p = MagicMock()
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


def _make_tender(
    tender_id: str,
    url: str = "https://example.com/t/1",
    title: str = "Title",
    price: float = 1_000_000,
):
    return {
        "tender_id": tender_id,
        "url": url,
        "title": title,
        "price": price,
    }


class TestRunSearchActive:
    """Тесты для run_search_active()."""

    @pytest.mark.asyncio
    async def test_no_active_tenders_found(self):
        """Если search_active_tenders вернул пустой список — ничего не сохраняем."""
        page = AsyncMock()
        params = _make_params()

        with (
            patch(
                "src.stages.search_active.search_active_tenders",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.stages.search_active.get_connection") as mock_conn_ctx,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_search_active(page, params)

            # Не должно быть вызовов upsert_customer / upsert_tender
            mock_conn.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_tender_with_inn_from_rostender(self):
        """ИНН найден на rostender.info — сохраняем заказчика и тендер."""
        page = AsyncMock()
        params = _make_params()
        tender = _make_tender("T-1")

        with (
            patch(
                "src.stages.search_active.search_active_tenders",
                new_callable=AsyncMock,
                return_value=[tender],
            ),
            patch(
                "src.stages.search_active.extract_inn_from_page",
                new_callable=AsyncMock,
                return_value="7712345678",
            ),
            patch(
                "src.stages.search_active.get_customer_name",
                new_callable=AsyncMock,
                return_value="ООО Тест",
            ),
            patch(
                "src.stages.search_active.upsert_customer", new_callable=AsyncMock
            ) as mock_upsert_cust,
            patch(
                "src.stages.search_active.upsert_tender", new_callable=AsyncMock
            ) as mock_upsert_tend,
            patch("src.stages.search_active.get_connection") as mock_conn_ctx,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_search_active(page, params)

            mock_upsert_cust.assert_called_once_with(
                mock_conn,
                inn="7712345678",
                name="ООО Тест",
            )
            mock_upsert_tend.assert_called_once_with(
                mock_conn,
                tender_id="T-1",
                customer_inn="7712345678",
                url=tender["url"],
                title=tender["title"],
                price=tender["price"],
                tender_status="active",
            )
            mock_conn.commit.assert_called()

    @pytest.mark.asyncio
    async def test_inn_fallback_to_eis(self):
        """ИНН не найден на rostender — фолбэк на ЕИС."""
        page = AsyncMock()
        params = _make_params()
        tender = _make_tender("T-2")

        with (
            patch(
                "src.stages.search_active.search_active_tenders",
                new_callable=AsyncMock,
                return_value=[tender],
            ),
            patch(
                "src.stages.search_active.extract_inn_from_page",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.stages.search_active.fallback_extract_inn",
                new_callable=AsyncMock,
                return_value="9900001111",
            ) as mock_fallback,
            patch(
                "src.stages.search_active.get_customer_name",
                new_callable=AsyncMock,
                return_value="Fallback Name",
            ),
            patch(
                "src.stages.search_active.upsert_customer", new_callable=AsyncMock
            ) as mock_upsert_cust,
            patch("src.stages.search_active.upsert_tender", new_callable=AsyncMock),
            patch("src.stages.search_active.get_connection") as mock_conn_ctx,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_search_active(page, params)

            mock_fallback.assert_called_once_with(page, tender["url"])
            mock_upsert_cust.assert_called_once_with(
                mock_conn,
                inn="9900001111",
                name="Fallback Name",
            )

    @pytest.mark.asyncio
    async def test_inn_not_found_skips_tender(self):
        """Ни на rostender, ни на ЕИС ИНН не найден — пропускаем тендер."""
        page = AsyncMock()
        params = _make_params()
        tender = _make_tender("T-3")

        with (
            patch(
                "src.stages.search_active.search_active_tenders",
                new_callable=AsyncMock,
                return_value=[tender],
            ),
            patch(
                "src.stages.search_active.extract_inn_from_page",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.stages.search_active.fallback_extract_inn",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.stages.search_active.upsert_customer", new_callable=AsyncMock
            ) as mock_upsert_cust,
            patch(
                "src.stages.search_active.upsert_tender", new_callable=AsyncMock
            ) as mock_upsert_tend,
            patch("src.stages.search_active.get_connection") as mock_conn_ctx,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_search_active(page, params)

            mock_upsert_cust.assert_not_called()
            mock_upsert_tend.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_tenders_processed(self):
        """Несколько тендеров — каждый обрабатывается."""
        page = AsyncMock()
        params = _make_params()
        tenders = [_make_tender("T-A"), _make_tender("T-B")]

        with (
            patch(
                "src.stages.search_active.search_active_tenders",
                new_callable=AsyncMock,
                return_value=tenders,
            ),
            patch(
                "src.stages.search_active.extract_inn_from_page",
                new_callable=AsyncMock,
                side_effect=["111", "222"],
            ),
            patch(
                "src.stages.search_active.get_customer_name",
                new_callable=AsyncMock,
                return_value="Name",
            ),
            patch(
                "src.stages.search_active.upsert_customer", new_callable=AsyncMock
            ) as mock_upsert_cust,
            patch(
                "src.stages.search_active.upsert_tender", new_callable=AsyncMock
            ) as mock_upsert_tend,
            patch("src.stages.search_active.get_connection") as mock_conn_ctx,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_search_active(page, params)

            assert mock_upsert_cust.call_count == 2
            assert mock_upsert_tend.call_count == 2

    @pytest.mark.asyncio
    async def test_passes_params_to_search(self):
        """Параметры из PipelineParams передаются в search_active_tenders."""
        page = AsyncMock()
        params = _make_params(
            keywords="ремонт",
            min_price_active=100_000,
            date_from="15.03.2024",
            date_to="20.03.2024",
        )

        with (
            patch(
                "src.stages.search_active.search_active_tenders",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_search,
            patch("src.stages.search_active.get_connection") as mock_conn_ctx,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_search_active(page, params)

            mock_search.assert_called_once_with(
                page,
                keywords="ремонт",
                min_price=100_000,
                date_from="15.03.2024",
                date_to="20.03.2024",
            )
