"""Tests for analyzer/competition.py."""

from __future__ import annotations

import pytest

from src.analyzer.competition import (
    CompetitionMetrics,
    calculate_metrics,
)
from tests.conftest import MockRow


class TestCalculateMetrics:
    """Tests for calculate_metrics function."""

    def test_all_success_high_competition(
        self,
        mock_row: type[MockRow],
        sample_analyses_success: list[dict],
    ) -> None:
        """Все протоколы успешно проанализированы, высокая конкуренция."""
        rows = [mock_row(data) for data in sample_analyses_success]

        metrics = calculate_metrics(
            rows,
            max_participants=2,
            ratio_threshold=0.8,
        )

        assert metrics.total_historical == 5
        assert metrics.total_analyzed == 5
        assert metrics.total_skipped == 0
        assert (
            metrics.low_competition_count == 4
        )  # t1(1), t2(2), t3(1), t5(2), t4=3 excluded
        assert metrics.competition_ratio == pytest.approx(0.8)
        assert metrics.is_interesting is True  # 0.8 >= 0.8
        assert metrics.is_determinable is True

    def test_all_success_low_competition(
        self,
        mock_row: type[MockRow],
    ) -> None:
        """Все протоколы успешно проанализированы, низкая конкуренция."""
        analyses = [
            {"tender_id": "t1", "parse_status": "success", "participants_count": 1},
            {"tender_id": "t2", "parse_status": "success", "participants_count": 2},
            {"tender_id": "t3", "parse_status": "success", "participants_count": 1},
            {"tender_id": "t4", "parse_status": "success", "participants_count": 1},
            {"tender_id": "t5", "parse_status": "success", "participants_count": 2},
        ]
        rows = [mock_row(data) for data in analyses]

        metrics = calculate_metrics(
            rows,
            max_participants=2,
            ratio_threshold=0.8,
        )

        assert metrics.total_historical == 5
        assert metrics.total_analyzed == 5
        assert metrics.low_competition_count == 5  # all 5 have <= 2 participants
        assert metrics.competition_ratio == pytest.approx(1.0)
        assert metrics.is_interesting is True
        assert metrics.is_determinable is True

    def test_mixed_results(
        self,
        mock_row: type[MockRow],
        sample_analyses_mixed: list[dict],
    ) -> None:
        """Смешанные результаты (success + failed/skipped)."""
        rows = [mock_row(data) for data in sample_analyses_mixed]

        metrics = calculate_metrics(
            rows,
            max_participants=2,
            ratio_threshold=0.8,
        )

        assert metrics.total_historical == 5
        assert metrics.total_analyzed == 3  # только success
        assert metrics.total_skipped == 2  # failed + skipped_scan
        assert metrics.low_competition_count == 3  # t1(1), t2(2), t5(1)
        assert metrics.competition_ratio == pytest.approx(1.0)
        assert metrics.is_interesting is True
        assert metrics.is_determinable is True

    def test_empty_analyses(self, mock_row: type[MockRow]) -> None:
        """Пустой список анализов."""
        metrics = calculate_metrics([], max_participants=2, ratio_threshold=0.8)

        assert metrics.total_historical == 0
        assert metrics.total_analyzed == 0
        assert metrics.total_skipped == 0
        assert metrics.low_competition_count == 0
        assert metrics.competition_ratio is None
        assert metrics.is_interesting is False
        assert metrics.is_determinable is False

    def test_all_failed(self, mock_row: type[MockRow]) -> None:
        """Все протоколы не удалось проанализировать."""
        analyses = [
            {"tender_id": "t1", "parse_status": "failed", "participants_count": None},
            {
                "tender_id": "t2",
                "parse_status": "skipped_scan",
                "participants_count": None,
            },
            {
                "tender_id": "t3",
                "parse_status": "no_protocol",
                "participants_count": None,
            },
        ]
        rows = [mock_row(data) for data in analyses]

        metrics = calculate_metrics(rows)

        assert metrics.total_historical == 3
        assert metrics.total_analyzed == 0
        assert metrics.total_skipped == 3
        assert metrics.low_competition_count == 0
        assert metrics.competition_ratio is None
        assert metrics.is_interesting is False
        assert metrics.is_determinable is False

    def test_threshold_edge_case(self, mock_row: type[MockRow]) -> None:
        """Граничный случай: ratio точно равен threshold."""
        analyses = [
            {"tender_id": "t1", "parse_status": "success", "participants_count": 1},
            {"tender_id": "t2", "parse_status": "success", "participants_count": 1},
            {"tender_id": "t3", "parse_status": "success", "participants_count": 3},
            {"tender_id": "t4", "parse_status": "success", "participants_count": 3},
            {"tender_id": "t5", "parse_status": "success", "participants_count": 3},
        ]
        rows = [mock_row(data) for data in analyses]

        metrics = calculate_metrics(
            rows,
            max_participants=2,
            ratio_threshold=0.4,  # 2/5 = 0.4
        )

        assert metrics.competition_ratio == pytest.approx(0.4)
        assert metrics.is_interesting is True

    def test_custom_thresholds(self, mock_row: type[MockRow]) -> None:
        """Пользовательские пороговые значения."""
        analyses = [
            {"tender_id": "t1", "parse_status": "success", "participants_count": 3},
            {"tender_id": "t2", "parse_status": "success", "participants_count": 4},
            {"tender_id": "t3", "parse_status": "success", "participants_count": 5},
        ]
        rows = [mock_row(data) for data in analyses]

        metrics = calculate_metrics(
            rows,
            max_participants=5,  # Более мягкий порог
            ratio_threshold=0.5,
        )

        assert metrics.low_competition_count == 3
        assert metrics.competition_ratio == pytest.approx(1.0)
        assert metrics.is_interesting is True

    def test_none_participants_not_counted(self, mock_row: type[MockRow]) -> None:
        """Участники с participants_count=None не считаются."""
        analyses = [
            {"tender_id": "t1", "parse_status": "success", "participants_count": None},
            {"tender_id": "t2", "parse_status": "success", "participants_count": 1},
        ]
        rows = [mock_row(data) for data in analyses]

        metrics = calculate_metrics(rows, max_participants=2)

        assert metrics.total_analyzed == 2
        assert metrics.low_competition_count == 1  # только t2


class TestCompetitionMetrics:
    """Tests for CompetitionMetrics dataclass."""

    def test_dataclass_fields(self) -> None:
        """Проверка полей дата-класса."""
        metrics = CompetitionMetrics(
            total_historical=10,
            total_analyzed=8,
            total_skipped=2,
            low_competition_count=6,
            competition_ratio=0.75,
            is_interesting=True,
            is_determinable=True,
        )

        assert metrics.total_historical == 10
        assert metrics.total_analyzed == 8
        assert metrics.total_skipped == 2
        assert metrics.low_competition_count == 6
        assert metrics.competition_ratio == 0.75
        assert metrics.is_interesting is True
        assert metrics.is_determinable is True
