"""Тесты для src/stages/extended_search.py — Этап 3: оркестрация."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.stages.extended_search import run_extended_search


def _make_params(**overrides):
    defaults = dict(
        keywords="строительство",
        min_price_related=300_000,
    )
    defaults.update(overrides)
    p = MagicMock()
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


def _make_customer(inn: str, name: str | None = None):
    return {"inn": inn, "name": name}


def _make_tender(
    tender_id: str,
    title: str = "Title",
    url: str = "https://example.com",
    price: float = 500_000,
):
    return {"tender_id": tender_id, "title": title, "url": url, "price": price}


class TestRunExtendedSearch:
    """Тесты для run_extended_search()."""

    @pytest.mark.asyncio
    async def test_no_interesting_customers(self):
        """Нет интересных заказчиков — ранний выход."""
        page = AsyncMock()
        params = _make_params()

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
            ) as mock_search,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)

            mock_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_error_continues_to_next(self):
        """Ошибка поиска тендеров для одного заказчика — продолжаем с другим."""
        page = AsyncMock()
        params = _make_params()
        customers = [
            _make_customer("ERR_INN", "Bad Customer"),
            _make_customer("OK_INN", "Good Customer"),
        ]

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=customers,
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("timeout"), []],
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should not raise
            await run_extended_search(page, params)

    @pytest.mark.asyncio
    async def test_no_tenders_found_for_customer(self):
        """Тендеры не найдены — переходим к следующему заказчику."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("5555555555", "Empty")

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.extended_search.update_customer_status",
                new_callable=AsyncMock,
            ) as mock_status,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)

            # No status update since we skip early
            mock_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_tender_skipped(self):
        """Тендер уже в БД — пропускаем."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("6666666666")
        tender = _make_tender("T-EXISTS")

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                return_value=[tender],
            ),
            patch(
                "src.stages.extended_search.tender_exists",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.stages.extended_search.result_exists", new_callable=AsyncMock
            ) as mock_result_exists,
            patch(
                "src.stages.extended_search.upsert_tender", new_callable=AsyncMock
            ) as mock_upsert,
            patch(
                "src.stages.extended_search.update_customer_status",
                new_callable=AsyncMock,
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)

            mock_upsert.assert_not_called()
            mock_result_exists.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_result_skipped(self):
        """Результат уже есть — пропускаем."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("7777777777")
        tender = _make_tender("T-RESULT")

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                return_value=[tender],
            ),
            patch(
                "src.stages.extended_search.tender_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.stages.extended_search.result_exists",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.stages.extended_search.upsert_tender", new_callable=AsyncMock
            ) as mock_upsert,
            patch(
                "src.stages.extended_search.update_customer_status",
                new_callable=AsyncMock,
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)

            mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_tender_saved_and_analyzed(self):
        """Новый тендер — сохраняем и анализируем историю."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("8888888888", "New Cust")
        tender = _make_tender("T-NEW", title="New Tender")

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                return_value=[tender],
            ),
            patch(
                "src.stages.extended_search.tender_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.stages.extended_search.result_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.stages.extended_search.upsert_tender", new_callable=AsyncMock
            ) as mock_upsert,
            patch(
                "src.stages.extended_search.update_customer_status",
                new_callable=AsyncMock,
            ),
            patch(
                "src.stages.extended_search.analyze_tender_history",
                new_callable=AsyncMock,
            ) as mock_analyze,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)

            mock_upsert.assert_called_once_with(
                mock_conn,
                tender_id="T-NEW",
                customer_inn="8888888888",
                url=tender["url"],
                title="New Tender",
                price=tender["price"],
                tender_status="active",
            )
            mock_analyze.assert_called_once()
            assert mock_analyze.call_args.kwargs["source"] == "extended"
            assert mock_analyze.call_args.kwargs["active_tender_id"] == "T-NEW"

    @pytest.mark.asyncio
    async def test_analyze_error_does_not_stop_processing(self):
        """Ошибка в analyze_tender_history — продолжаем с другими тендерами."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("9999999999")
        tenders = [_make_tender("T-ERR"), _make_tender("T-OK")]

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                return_value=tenders,
            ),
            patch(
                "src.stages.extended_search.tender_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.stages.extended_search.result_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.stages.extended_search.upsert_tender", new_callable=AsyncMock),
            patch(
                "src.stages.extended_search.update_customer_status",
                new_callable=AsyncMock,
            ) as mock_status,
            patch(
                "src.stages.extended_search.analyze_tender_history",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("fail"), None],
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)

            # Status should still be updated to extended_analyzed at the end
            last_status = mock_status.call_args_list[-1]
            assert last_status[0][2] == "extended_analyzed"

    @pytest.mark.asyncio
    async def test_status_transitions(self):
        """Статус заказчика: extended_processing → extended_analyzed."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("1010101010")
        tender = _make_tender("T-ST")

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                return_value=[tender],
            ),
            patch(
                "src.stages.extended_search.tender_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.stages.extended_search.result_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.stages.extended_search.upsert_tender", new_callable=AsyncMock),
            patch(
                "src.stages.extended_search.update_customer_status",
                new_callable=AsyncMock,
            ) as mock_status,
            patch(
                "src.stages.extended_search.analyze_tender_history",
                new_callable=AsyncMock,
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)

            statuses = [c[0][2] for c in mock_status.call_args_list]
            assert statuses == ["extended_processing", "extended_analyzed"]

    @pytest.mark.asyncio
    async def test_passes_params_to_search(self):
        """Параметры передаются в search_tenders_by_inn."""
        page = AsyncMock()
        params = _make_params(keywords="ремонт", min_price_related=999)
        customer = _make_customer("PASS_INN")

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_search,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)

            mock_search.assert_called_once_with(
                page,
                "PASS_INN",
                keywords="ремонт",
                min_price=999,
            )

    @pytest.mark.asyncio
    async def test_customer_name_fallback_to_inn(self):
        """name=None — не вызывает ошибку (fallback к ИНН в логировании)."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("NONAME_INN", name=None)

        with (
            patch("src.stages.extended_search.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.extended_search.get_interesting_customers",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.extended_search.search_tenders_by_inn",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_extended_search(page, params)
