"""Tests for src.stages.params — PipelineParams dataclass and factory."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import pytest

from src.stages.params import PipelineParams


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_namespace(**overrides) -> argparse.Namespace:
    """Create an argparse.Namespace with sensible defaults (all None)."""
    defaults = {
        "keywords": None,
        "min_price": None,
        "min_price_related": None,
        "min_price_historical": None,
        "history_limit": None,
        "max_participants": None,
        "ratio_threshold": None,
        "date_from": None,
        "date_to": None,
        "days_back": 7,
        "dry_run": False,
        "headless": True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ── TestPipelineParams ───────────────────────────────────────────────────────


class TestPipelineParamsFromArgs:
    """Tests for PipelineParams.from_args factory method."""

    def test_defaults_from_config(self) -> None:
        """When all CLI args are None, values come from config.yaml defaults."""
        args = _make_namespace()
        params = PipelineParams.from_args(args)

        # Should use config defaults (imported at module level in params.py)
        assert isinstance(params.keywords, list)
        assert len(params.keywords) > 0
        assert params.min_price_active > 0
        assert params.min_price_related > 0
        assert params.min_price_historical > 0
        assert params.history_limit > 0
        assert params.max_participants > 0
        assert 0.0 < params.ratio_threshold <= 1.0
        assert isinstance(params.output_formats, list)

    def test_cli_keywords_override(self) -> None:
        """CLI --keywords should override config defaults."""
        args = _make_namespace(keywords=["test1", "test2"])
        params = PipelineParams.from_args(args)

        assert params.keywords == ["test1", "test2"]

    def test_cli_min_price_override(self) -> None:
        """CLI --min-price should override config default."""
        args = _make_namespace(min_price=999)
        params = PipelineParams.from_args(args)

        assert params.min_price_active == 999

    def test_cli_min_price_related_override(self) -> None:
        """CLI --min-price-related should override config default."""
        args = _make_namespace(min_price_related=500)
        params = PipelineParams.from_args(args)

        assert params.min_price_related == 500

    def test_cli_min_price_historical_override(self) -> None:
        """CLI --min-price-historical should override config default."""
        args = _make_namespace(min_price_historical=100)
        params = PipelineParams.from_args(args)

        assert params.min_price_historical == 100

    def test_cli_history_limit_override(self) -> None:
        """CLI --history-limit should override config default."""
        args = _make_namespace(history_limit=10)
        params = PipelineParams.from_args(args)

        assert params.history_limit == 10

    def test_cli_max_participants_override(self) -> None:
        """CLI --max-participants should override config default."""
        args = _make_namespace(max_participants=5)
        params = PipelineParams.from_args(args)

        assert params.max_participants == 5

    def test_cli_ratio_threshold_override(self) -> None:
        """CLI --ratio-threshold should override config default."""
        args = _make_namespace(ratio_threshold=0.5)
        params = PipelineParams.from_args(args)

        assert params.ratio_threshold == 0.5

    def test_frozen_dataclass(self) -> None:
        """PipelineParams should be immutable (frozen)."""
        args = _make_namespace()
        params = PipelineParams.from_args(args)

        with pytest.raises(AttributeError):
            params.min_price_active = 0  # type: ignore[misc]

    def test_headless_default_true(self) -> None:
        """By default headless should be True."""
        args = _make_namespace()
        params = PipelineParams.from_args(args)

        assert params.headless is True

    def test_headless_false_when_no_headless(self) -> None:
        """--no-headless sets headless=False."""
        args = _make_namespace(headless=False)
        params = PipelineParams.from_args(args)

        assert params.headless is False

    def test_headless_fallback_when_attr_missing(self) -> None:
        """If headless attr is missing from Namespace, defaults to True."""
        args = _make_namespace()
        delattr(args, "headless")  # simulate old-style namespace without headless
        params = PipelineParams.from_args(args)

        assert params.headless is True


class TestResolveDates:
    """Tests for PipelineParams._resolve_dates logic."""

    def test_explicit_dates_passthrough(self) -> None:
        """Explicit --date-from and --date-to should be passed through."""
        args = _make_namespace(date_from="01.01.2025", date_to="31.01.2025")
        params = PipelineParams.from_args(args)

        assert params.date_from == "01.01.2025"
        assert params.date_to == "31.01.2025"

    def test_only_date_from(self) -> None:
        """Only --date-from should pass through, date_to is None."""
        args = _make_namespace(date_from="01.01.2025")
        params = PipelineParams.from_args(args)

        assert params.date_from == "01.01.2025"
        assert params.date_to is None

    def test_only_date_to(self) -> None:
        """Only --date-to should pass through, date_from is None."""
        args = _make_namespace(date_to="31.01.2025")
        params = PipelineParams.from_args(args)

        assert params.date_from is None
        assert params.date_to == "31.01.2025"

    def test_days_back_default(self) -> None:
        """No explicit dates → auto-compute from --days-back (default 7)."""
        args = _make_namespace(days_back=7)
        params = PipelineParams.from_args(args)

        expected_to = datetime.now().strftime("%d.%m.%Y")
        expected_from = (datetime.now() - timedelta(days=7)).strftime("%d.%m.%Y")

        assert params.date_to == expected_to
        assert params.date_from == expected_from

    def test_days_back_custom(self) -> None:
        """Custom --days-back should compute correct date range."""
        args = _make_namespace(days_back=30)
        params = PipelineParams.from_args(args)

        expected_to = datetime.now().strftime("%d.%m.%Y")
        expected_from = (datetime.now() - timedelta(days=30)).strftime("%d.%m.%Y")

        assert params.date_to == expected_to
        assert params.date_from == expected_from

    def test_days_back_zero(self) -> None:
        """--days-back=0 means both dates are today."""
        args = _make_namespace(days_back=0)
        params = PipelineParams.from_args(args)

        today = datetime.now().strftime("%d.%m.%Y")
        assert params.date_from == today
        assert params.date_to == today
