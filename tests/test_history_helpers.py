"""Tests for src.stages._history_helpers — shared historical analysis logic."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.analyzer.competition import CompetitionMetrics
from src.stages._history_helpers import HistoryAnalysisResult, analyze_tender_history
from src.stages.params import PipelineParams


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_params(**overrides) -> PipelineParams:
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
        "output_formats": ["console"],
        "headless": True,
    }
    defaults.update(overrides)
    return PipelineParams(**defaults)


def _fake_protocol_result(status: str = "success"):
    """Create a mock ProtocolParseResult."""
    mock = MagicMock()
    mock.parse_status = status
    return mock


def _fake_metrics(
    is_determinable: bool = True,
    is_interesting: bool = False,
    **kwargs,
) -> CompetitionMetrics:
    defaults = {
        "total_historical": 3,
        "total_analyzed": 2,
        "total_skipped": 1,
        "low_competition_count": 1,
        "competition_ratio": 0.5,
        "is_interesting": is_interesting,
        "is_determinable": is_determinable,
    }
    defaults.update(kwargs)
    return CompetitionMetrics(**defaults)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestHistoryAnalysisResult:
    """Tests for the HistoryAnalysisResult dataclass."""

    def test_fields(self) -> None:
        r = HistoryAnalysisResult(
            historical_count=5,
            success_count=3,
            failed_count=2,
            metrics=None,
            saved=False,
        )
        assert r.historical_count == 5
        assert r.success_count == 3
        assert r.failed_count == 2
        assert r.metrics is None
        assert r.saved is False

    def test_with_metrics(self) -> None:
        m = _fake_metrics()
        r = HistoryAnalysisResult(
            historical_count=3,
            success_count=2,
            failed_count=1,
            metrics=m,
            saved=True,
        )
        assert r.metrics is m
        assert r.saved is True


class TestAnalyzeTenderHistory:
    """Tests for analyze_tender_history async function."""

    @pytest.mark.asyncio
    async def test_no_historical_tenders(self) -> None:
        """When search returns no historical tenders, returns empty result."""
        page = MagicMock()
        conn = AsyncMock()
        params = _make_params()

        with (
            patch(
                "src.stages._history_helpers.extract_keywords_from_title",
                return_value=["kw1"],
            ),
            patch(
                "src.stages._history_helpers.search_historical_tenders",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await analyze_tender_history(
                page,
                conn,
                active_tender_id="t1",
                tender_title="Test tender",
                customer_inn="123",
                params=params,
            )

        assert result.historical_count == 0
        assert result.success_count == 0
        assert result.failed_count == 0
        assert result.metrics is None
        assert result.saved is False

    @pytest.mark.asyncio
    async def test_historical_tenders_found_and_analyzed(self) -> None:
        """When historical tenders are found, they are saved, parsed, and metrics calculated."""
        page = MagicMock()
        conn = AsyncMock()
        conn.commit = AsyncMock()
        params = _make_params()

        historical_data = [
            {"tender_id": "h1", "url": "http://t/h1", "title": "H1", "price": 100},
            {"tender_id": "h2", "url": "http://t/h2", "title": "H2", "price": 200},
        ]

        metrics = _fake_metrics(is_determinable=True, is_interesting=True)

        with (
            patch(
                "src.stages._history_helpers.extract_keywords_from_title",
                return_value=["kw"],
            ),
            patch(
                "src.stages._history_helpers.search_historical_tenders",
                new_callable=AsyncMock,
                return_value=historical_data,
            ),
            patch(
                "src.stages._history_helpers.upsert_tender",
                new_callable=AsyncMock,
            ) as mock_upsert,
            patch(
                "src.stages._history_helpers.analyze_tender_protocol",
                new_callable=AsyncMock,
                return_value=_fake_protocol_result("success"),
            ) as mock_proto,
            patch(
                "src.stages._history_helpers.get_latest_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.calculate_metrics",
                return_value=metrics,
            ),
            patch("src.stages._history_helpers.log_metrics"),
            patch(
                "src.stages._history_helpers.result_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.stages._history_helpers.insert_result",
                new_callable=AsyncMock,
            ) as mock_insert,
        ):
            result = await analyze_tender_history(
                page,
                conn,
                active_tender_id="t1",
                tender_title="Test",
                customer_inn="123",
                params=params,
                source="primary",
            )

        assert result.historical_count == 2
        assert result.success_count == 2
        assert result.failed_count == 0
        assert result.metrics is metrics
        assert result.saved is True
        assert mock_upsert.call_count == 2
        assert mock_proto.call_count == 2
        mock_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_result_already_exists_skips_insert(self) -> None:
        """When result already exists for this tender, skip insert."""
        page = MagicMock()
        conn = AsyncMock()
        conn.commit = AsyncMock()
        params = _make_params()

        historical_data = [
            {"tender_id": "h1", "url": "http://t/h1", "title": "H1", "price": 100},
        ]

        metrics = _fake_metrics(is_determinable=True, is_interesting=True)

        with (
            patch(
                "src.stages._history_helpers.extract_keywords_from_title",
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.search_historical_tenders",
                new_callable=AsyncMock,
                return_value=historical_data,
            ),
            patch(
                "src.stages._history_helpers.upsert_tender",
                new_callable=AsyncMock,
            ),
            patch(
                "src.stages._history_helpers.analyze_tender_protocol",
                new_callable=AsyncMock,
                return_value=_fake_protocol_result("success"),
            ),
            patch(
                "src.stages._history_helpers.get_latest_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.calculate_metrics",
                return_value=metrics,
            ),
            patch("src.stages._history_helpers.log_metrics"),
            patch(
                "src.stages._history_helpers.result_exists",
                new_callable=AsyncMock,
                return_value=True,  # already exists
            ),
            patch(
                "src.stages._history_helpers.insert_result",
                new_callable=AsyncMock,
            ) as mock_insert,
        ):
            result = await analyze_tender_history(
                page,
                conn,
                active_tender_id="t1",
                tender_title="Test",
                customer_inn="123",
                params=params,
            )

        assert result.saved is False
        mock_insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_determinable_skips_insert(self) -> None:
        """When metrics are not determinable, don't insert result."""
        page = MagicMock()
        conn = AsyncMock()
        conn.commit = AsyncMock()
        params = _make_params()

        historical_data = [
            {"tender_id": "h1", "url": "http://t/h1", "title": "H1", "price": 100},
        ]

        metrics = _fake_metrics(is_determinable=False)

        with (
            patch(
                "src.stages._history_helpers.extract_keywords_from_title",
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.search_historical_tenders",
                new_callable=AsyncMock,
                return_value=historical_data,
            ),
            patch(
                "src.stages._history_helpers.upsert_tender",
                new_callable=AsyncMock,
            ),
            patch(
                "src.stages._history_helpers.analyze_tender_protocol",
                new_callable=AsyncMock,
                return_value=_fake_protocol_result("failed"),
            ),
            patch(
                "src.stages._history_helpers.get_latest_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.calculate_metrics",
                return_value=metrics,
            ),
            patch("src.stages._history_helpers.log_metrics"),
            patch(
                "src.stages._history_helpers.result_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.stages._history_helpers.insert_result",
                new_callable=AsyncMock,
            ) as mock_insert,
        ):
            result = await analyze_tender_history(
                page,
                conn,
                active_tender_id="t1",
                tender_title="Test",
                customer_inn="123",
                params=params,
            )

        assert result.saved is False
        mock_insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_protocol_parse_exception_counted_as_failed(self) -> None:
        """When protocol parsing raises, it's counted as failed."""
        page = MagicMock()
        conn = AsyncMock()
        conn.commit = AsyncMock()
        params = _make_params()

        historical_data = [
            {"tender_id": "h1", "url": "http://t/h1", "title": "H1", "price": 100},
            {"tender_id": "h2", "url": "http://t/h2", "title": "H2", "price": 200},
        ]

        metrics = _fake_metrics(is_determinable=False)

        with (
            patch(
                "src.stages._history_helpers.extract_keywords_from_title",
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.search_historical_tenders",
                new_callable=AsyncMock,
                return_value=historical_data,
            ),
            patch(
                "src.stages._history_helpers.upsert_tender",
                new_callable=AsyncMock,
            ),
            patch(
                "src.stages._history_helpers.analyze_tender_protocol",
                new_callable=AsyncMock,
                side_effect=Exception("parse error"),
            ),
            patch(
                "src.stages._history_helpers.get_latest_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.calculate_metrics",
                return_value=metrics,
            ),
            patch("src.stages._history_helpers.log_metrics"),
            patch(
                "src.stages._history_helpers.result_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await analyze_tender_history(
                page,
                conn,
                active_tender_id="t1",
                tender_title="Test",
                customer_inn="123",
                params=params,
            )

        assert result.success_count == 0
        assert result.failed_count == 2

    @pytest.mark.asyncio
    async def test_source_passed_to_insert_result(self) -> None:
        """The source parameter should be passed to insert_result."""
        page = MagicMock()
        conn = AsyncMock()
        conn.commit = AsyncMock()
        params = _make_params()

        historical_data = [
            {"tender_id": "h1", "url": "http://t/h1", "title": "H1", "price": 100},
        ]

        metrics = _fake_metrics(is_determinable=True, is_interesting=True)

        with (
            patch(
                "src.stages._history_helpers.extract_keywords_from_title",
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.search_historical_tenders",
                new_callable=AsyncMock,
                return_value=historical_data,
            ),
            patch(
                "src.stages._history_helpers.upsert_tender",
                new_callable=AsyncMock,
            ),
            patch(
                "src.stages._history_helpers.analyze_tender_protocol",
                new_callable=AsyncMock,
                return_value=_fake_protocol_result("success"),
            ),
            patch(
                "src.stages._history_helpers.get_latest_protocol_analyses",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.stages._history_helpers.calculate_metrics",
                return_value=metrics,
            ),
            patch("src.stages._history_helpers.log_metrics"),
            patch(
                "src.stages._history_helpers.result_exists",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.stages._history_helpers.insert_result",
                new_callable=AsyncMock,
            ) as mock_insert,
        ):
            await analyze_tender_history(
                page,
                conn,
                active_tender_id="t1",
                tender_title="Test",
                customer_inn="123",
                params=params,
                source="extended",
            )

        # Verify source="extended" was passed
        call_kwargs = mock_insert.call_args[1]
        assert call_kwargs["source"] == "extended"

    @pytest.mark.asyncio
    async def test_empty_title_handled(self) -> None:
        """None or empty tender_title should not crash."""
        page = MagicMock()
        conn = AsyncMock()
        conn.commit = AsyncMock()
        params = _make_params()

        with (
            patch(
                "src.stages._history_helpers.extract_keywords_from_title",
                return_value=[],
            ) as mock_kw,
            patch(
                "src.stages._history_helpers.search_historical_tenders",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await analyze_tender_history(
                page,
                conn,
                active_tender_id="t1",
                tender_title=None,  # type: ignore[arg-type]
                customer_inn="123",
                params=params,
            )

        # Should have called extract_keywords_from_title with ""
        mock_kw.assert_called_once_with("")
        assert result.historical_count == 0
