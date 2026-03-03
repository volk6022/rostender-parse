"""Общие параметры pipeline — dataclass + фабрика из CLI-аргументов."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.config import (
    SEARCH_KEYWORDS as DEFAULT_KEYWORDS,
    MIN_PRICE_ACTIVE as DEFAULT_MIN_PRICE_ACTIVE,
    MIN_PRICE_RELATED as DEFAULT_MIN_PRICE_RELATED,
    MIN_PRICE_HISTORICAL as DEFAULT_MIN_PRICE_HISTORICAL,
    HISTORICAL_TENDERS_LIMIT as DEFAULT_HISTORY_LIMIT,
    MAX_PARTICIPANTS_THRESHOLD as DEFAULT_MAX_PARTICIPANTS,
    COMPETITION_RATIO_THRESHOLD as DEFAULT_RATIO_THRESHOLD,
    SEARCH_DATE_FROM as DEFAULT_DATE_FROM,
    SEARCH_DATE_TO as DEFAULT_DATE_TO,
    OUTPUT_FORMATS as DEFAULT_OUTPUT_FORMATS,
)


@dataclass(frozen=True)
class PipelineParams:
    """Неизменяемый набор параметров, общий для всех этапов pipeline."""

    keywords: list[str]
    min_price_active: int
    min_price_related: int
    min_price_historical: int
    history_limit: int
    max_participants: int
    ratio_threshold: float
    date_from: str | None
    date_to: str | None
    output_formats: list[str]
    headless: bool

    # ── Фабрика ──────────────────────────────────────────────────────────────

    @staticmethod
    def from_args(args: argparse.Namespace) -> PipelineParams:
        """Создаёт PipelineParams, объединяя CLI-аргументы и дефолты из config.yaml."""

        keywords = args.keywords if args.keywords else DEFAULT_KEYWORDS

        min_price_active = (
            args.min_price if args.min_price is not None else DEFAULT_MIN_PRICE_ACTIVE
        )
        min_price_related = (
            args.min_price_related
            if args.min_price_related is not None
            else DEFAULT_MIN_PRICE_RELATED
        )
        min_price_historical = (
            args.min_price_historical
            if args.min_price_historical is not None
            else DEFAULT_MIN_PRICE_HISTORICAL
        )
        history_limit = (
            args.history_limit
            if args.history_limit is not None
            else DEFAULT_HISTORY_LIMIT
        )
        max_participants = (
            args.max_participants
            if args.max_participants is not None
            else DEFAULT_MAX_PARTICIPANTS
        )
        ratio_threshold = (
            args.ratio_threshold
            if args.ratio_threshold is not None
            else DEFAULT_RATIO_THRESHOLD
        )

        date_from, date_to = PipelineParams._resolve_dates(args)

        headless = getattr(args, "headless", True)

        return PipelineParams(
            keywords=keywords,
            min_price_active=min_price_active,
            min_price_related=min_price_related,
            min_price_historical=min_price_historical,
            history_limit=history_limit,
            max_participants=max_participants,
            ratio_threshold=ratio_threshold,
            date_from=date_from,
            date_to=date_to,
            output_formats=DEFAULT_OUTPUT_FORMATS,
            headless=headless,
        )

    # ── Внутренние хелперы ───────────────────────────────────────────────────

    @staticmethod
    def _resolve_dates(args: argparse.Namespace) -> tuple[str | None, str | None]:
        """Определить даты поиска на основе аргументов."""
        if args.date_from or args.date_to:
            return args.date_from, args.date_to

        if DEFAULT_DATE_FROM or DEFAULT_DATE_TO:
            return DEFAULT_DATE_FROM, DEFAULT_DATE_TO

        date_to = datetime.now().strftime("%d.%m.%Y")
        date_from = (datetime.now() - timedelta(days=args.days_back)).strftime(
            "%d.%m.%Y"
        )
        return date_from, date_to
