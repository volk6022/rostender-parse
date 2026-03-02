"""Tests for src.stages.report — Stage 4 orchestration."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.stages.params import PipelineParams
from src.stages.report import run_report


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_params(**overrides) -> PipelineParams:
    """Create PipelineParams with sensible defaults."""
    defaults = {
        "keywords": ["test"],
        "min_price_active": 1000,
        "min_price_related": 500,
        "min_price_historical": 100,
        "history_limit": 5,
        "max_participants": 2,
        "ratio_threshold": 0.8,
        "date_from": "01.01.2025",
        "date_to": "31.01.2025",
        "output_formats": ["console", "excel"],
        "headless": True,
    }
    defaults.update(overrides)
    return PipelineParams(**defaults)


def _mock_get_connection():
    """Create a mock async context manager for get_connection."""
    mock_conn = AsyncMock()

    class _FakeCtx:
        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, *args):
            pass

    return _FakeCtx(), mock_conn


# ── Tests ────────────────────────────────────────────────────────────────────


class TestRunReport:
    """Tests for run_report orchestration."""

    @pytest.mark.asyncio
    async def test_calls_console_report_when_console_format(self) -> None:
        """When 'console' is in output_formats, print_console_report is called."""
        params = _make_params(output_formats=["console"])
        ctx, mock_conn = _mock_get_connection()

        mock_conn.execute = AsyncMock()

        with (
            patch("src.stages.report.get_connection", return_value=ctx),
            patch(
                "src.stages.report.get_interesting_results",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_results",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_customers",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.stages.report.print_console_report") as mock_print,
            patch("src.stages.report.log_console_summary") as mock_log,
            patch("src.stages.report.generate_excel_report") as mock_excel,
        ):
            await run_report(params)

            mock_print.assert_called_once_with([], [], [])
            mock_log.assert_called_once_with(0, 0)
            mock_excel.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_excel_report_when_excel_format(self) -> None:
        """When 'excel' is in output_formats, generate_excel_report is called."""
        params = _make_params(output_formats=["excel"])
        ctx, mock_conn = _mock_get_connection()

        with (
            patch("src.stages.report.get_connection", return_value=ctx),
            patch(
                "src.stages.report.get_interesting_results",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_results",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_customers",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.stages.report.print_console_report") as mock_print,
            patch(
                "src.stages.report.generate_excel_report",
                return_value=Path("report.xlsx"),
            ) as mock_excel,
        ):
            await run_report(params)

            mock_print.assert_not_called()
            mock_excel.assert_called_once_with([], [], [], [])

    @pytest.mark.asyncio
    async def test_calls_both_when_both_formats(self) -> None:
        """When both formats are specified, both reporters are called."""
        params = _make_params(output_formats=["console", "excel"])
        ctx, mock_conn = _mock_get_connection()

        with (
            patch("src.stages.report.get_connection", return_value=ctx),
            patch(
                "src.stages.report.get_interesting_results",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_results",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_customers",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.stages.report.print_console_report") as mock_print,
            patch("src.stages.report.log_console_summary") as mock_log,
            patch(
                "src.stages.report.generate_excel_report",
                return_value=Path("report.xlsx"),
            ) as mock_excel,
        ):
            await run_report(params)

            mock_print.assert_called_once()
            mock_log.assert_called_once()
            mock_excel.assert_called_once()

    @pytest.mark.asyncio
    async def test_calls_neither_when_empty_formats(self) -> None:
        """When output_formats is empty, no reporters are called."""
        params = _make_params(output_formats=[])
        ctx, mock_conn = _mock_get_connection()

        with (
            patch("src.stages.report.get_connection", return_value=ctx),
            patch(
                "src.stages.report.get_interesting_results",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_results",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_customers",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages.report.get_all_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("src.stages.report.print_console_report") as mock_print,
            patch("src.stages.report.generate_excel_report") as mock_excel,
        ):
            await run_report(params)

            mock_print.assert_not_called()
            mock_excel.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_db_data_to_reporters(self) -> None:
        """DB query results are passed correctly to reporters."""
        params = _make_params(output_formats=["console", "excel"])
        ctx, mock_conn = _mock_get_connection()

        fake_interesting = [{"id": 1}]
        fake_results = [{"id": 2}]
        fake_customers = [{"id": 3}]
        fake_protocols = [{"id": 4}]

        with (
            patch("src.stages.report.get_connection", return_value=ctx),
            patch(
                "src.stages.report.get_interesting_results",
                new_callable=AsyncMock,
                return_value=fake_interesting,
            ),
            patch(
                "src.stages.report.get_all_results",
                new_callable=AsyncMock,
                return_value=fake_results,
            ),
            patch(
                "src.stages.report.get_all_customers",
                new_callable=AsyncMock,
                return_value=fake_customers,
            ),
            patch(
                "src.stages.report.get_all_protocol_analyses",
                new_callable=AsyncMock,
                return_value=fake_protocols,
            ),
            patch("src.stages.report.print_console_report") as mock_print,
            patch("src.stages.report.log_console_summary") as mock_log,
            patch(
                "src.stages.report.generate_excel_report", return_value=Path("r.xlsx")
            ) as mock_excel,
        ):
            await run_report(params)

            mock_print.assert_called_once_with(
                fake_interesting, fake_results, fake_customers
            )
            mock_log.assert_called_once_with(
                1, 1
            )  # len(customers)=1, len(interesting)=1
            mock_excel.assert_called_once_with(
                fake_interesting, fake_results, fake_customers, fake_protocols
            )
