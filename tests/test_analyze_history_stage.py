"""Тесты для src/stages/analyze_history.py — Этап 2: оркестрация."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.stages.analyze_history import run_analyze_history


def _make_params():
    return MagicMock()


def _make_customer(inn: str, name: str | None = None):
    return {"inn": inn, "name": name}


def _make_tender(tender_id: str, title: str = "Tender Title"):
    return {"tender_id": tender_id, "title": title}


class TestRunAnalyzeHistory:
    """Тесты для run_analyze_history()."""

    @pytest.mark.asyncio
    async def test_no_new_customers(self):
        """Если нет заказчиков со статусом 'new' — сразу выходим."""
        page = AsyncMock()
        params = _make_params()

        with (
            patch("src.stages.analyze_history.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.analyze_history.get_customers_by_status",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.analyze_history.analyze_tender_history",
                new_callable=AsyncMock,
            ) as mock_analyze,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_analyze_history(page, params)

            mock_analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_customer_with_no_active_tenders(self):
        """Заказчик есть, но активных тендеров нет — статус → analyzed."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("1234567890", "ООО Тест")

        with (
            patch("src.stages.analyze_history.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.analyze_history.get_customers_by_status",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.analyze_history.get_tenders_by_customer",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.analyze_history.update_customer_status",
                new_callable=AsyncMock,
            ) as mock_update_status,
            patch(
                "src.stages.analyze_history.analyze_tender_history",
                new_callable=AsyncMock,
            ) as mock_analyze,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_analyze_history(page, params)

            mock_analyze.assert_not_called()
            # Вызов update_customer_status: processing, затем analyzed
            status_calls = [c for c in mock_update_status.call_args_list]
            statuses = [c[0][2] for c in status_calls]  # 3rd positional arg
            assert "processing" in statuses
            assert "analyzed" in statuses

    @pytest.mark.asyncio
    async def test_customer_with_active_tenders_analyzed(self):
        """Заказчик с тендерами — analyze_tender_history вызывается для каждого."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("1111111111", "ООО Анализ")
        tenders = [_make_tender("T-1", "Title A"), _make_tender("T-2", "Title B")]

        with (
            patch("src.stages.analyze_history.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.analyze_history.get_customers_by_status",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.analyze_history.get_tenders_by_customer",
                new_callable=AsyncMock,
                return_value=tenders,
            ),
            patch(
                "src.stages.analyze_history.update_customer_status",
                new_callable=AsyncMock,
            ) as mock_update_status,
            patch(
                "src.stages.analyze_history.analyze_tender_history",
                new_callable=AsyncMock,
            ) as mock_analyze,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_analyze_history(page, params)

            assert mock_analyze.call_count == 2
            # Verify first call args
            first_call = mock_analyze.call_args_list[0]
            assert first_call.kwargs["active_tender_id"] == "T-1"
            assert first_call.kwargs["customer_inn"] == "1111111111"
            assert first_call.kwargs["source"] == "primary"

    @pytest.mark.asyncio
    async def test_exception_sets_error_status(self):
        """Исключение при обработке — статус заказчика → error."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("2222222222")
        tenders = [_make_tender("T-ERR")]

        with (
            patch("src.stages.analyze_history.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.analyze_history.get_customers_by_status",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.analyze_history.get_tenders_by_customer",
                new_callable=AsyncMock,
                return_value=tenders,
            ),
            patch(
                "src.stages.analyze_history.update_customer_status",
                new_callable=AsyncMock,
            ) as mock_update_status,
            patch(
                "src.stages.analyze_history.analyze_tender_history",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Network error"),
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_analyze_history(page, params)

            # Last status update should be "error"
            last_status_call = mock_update_status.call_args_list[-1]
            assert last_status_call[0][2] == "error"

    @pytest.mark.asyncio
    async def test_customer_name_fallback_to_inn(self):
        """Если name=None, используется ИНН как имя (для логирования)."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("3333333333", name=None)

        with (
            patch("src.stages.analyze_history.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.analyze_history.get_customers_by_status",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.analyze_history.get_tenders_by_customer",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.analyze_history.update_customer_status",
                new_callable=AsyncMock,
            ),
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should not raise — name fallback to inn in logging
            await run_analyze_history(page, params)

    @pytest.mark.asyncio
    async def test_multiple_customers_processed(self):
        """Несколько заказчиков — каждый обрабатывается."""
        page = AsyncMock()
        params = _make_params()
        customers = [
            _make_customer("AAA", "Customer A"),
            _make_customer("BBB", "Customer B"),
        ]

        with (
            patch("src.stages.analyze_history.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.analyze_history.get_customers_by_status",
                new_callable=AsyncMock,
                return_value=customers,
            ),
            patch(
                "src.stages.analyze_history.get_tenders_by_customer",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.analyze_history.update_customer_status",
                new_callable=AsyncMock,
            ) as mock_update_status,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_analyze_history(page, params)

            # processing + analyzed for each customer = 4 calls total
            inn_args = [c[0][1] for c in mock_update_status.call_args_list]
            assert "AAA" in inn_args
            assert "BBB" in inn_args

    @pytest.mark.asyncio
    async def test_tender_title_none_handled(self):
        """tender['title'] = None — должно обработаться как пустая строка."""
        page = AsyncMock()
        params = _make_params()
        customer = _make_customer("4444444444")
        tender = {"tender_id": "T-NULL", "title": None}

        with (
            patch("src.stages.analyze_history.get_connection") as mock_conn_ctx,
            patch(
                "src.stages.analyze_history.get_customers_by_status",
                new_callable=AsyncMock,
                return_value=[customer],
            ),
            patch(
                "src.stages.analyze_history.get_tenders_by_customer",
                new_callable=AsyncMock,
                return_value=[tender],
            ),
            patch(
                "src.stages.analyze_history.update_customer_status",
                new_callable=AsyncMock,
            ),
            patch(
                "src.stages.analyze_history.analyze_tender_history",
                new_callable=AsyncMock,
            ) as mock_analyze,
        ):
            mock_conn = AsyncMock()
            mock_conn_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_analyze_history(page, params)

            # tender_title should be "" (empty string via `or ""`)
            assert mock_analyze.call_args.kwargs["tender_title"] == ""
