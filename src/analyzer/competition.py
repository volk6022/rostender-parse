"""Расчёт метрик конкуренции для анализа тендеров."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.config import (
    COMPETITION_RATIO_THRESHOLD,
    MAX_PARTICIPANTS_THRESHOLD,
)


@dataclass
class CompetitionMetrics:
    total_historical: int
    total_analyzed: int
    total_skipped: int
    low_competition_count: int
    competition_ratio: float | None
    is_interesting: bool
    is_determinable: bool


def calculate_metrics(
    analyses: Sequence[Any],
    max_participants: int = MAX_PARTICIPANTS_THRESHOLD,
    ratio_threshold: float = COMPETITION_RATIO_THRESHOLD,
) -> CompetitionMetrics:
    total_historical = len(analyses)
    total_analyzed = 0
    total_skipped = 0
    low_competition_count = 0

    for row in analyses:
        parse_status = row["parse_status"]
        participants_count = row["participants_count"]

        if parse_status == "success":
            total_analyzed += 1
            if (
                participants_count is not None
                and participants_count <= max_participants
            ):
                low_competition_count += 1
        else:
            total_skipped += 1

    is_determinable = total_analyzed > 0

    if is_determinable:
        competition_ratio = low_competition_count / total_analyzed
        is_interesting = competition_ratio >= ratio_threshold
    else:
        competition_ratio = None
        is_interesting = False

    return CompetitionMetrics(
        total_historical=total_historical,
        total_analyzed=total_analyzed,
        total_skipped=total_skipped,
        low_competition_count=low_competition_count,
        competition_ratio=competition_ratio,
        is_interesting=is_interesting,
        is_determinable=is_determinable,
    )


def log_metrics(customer_inn: str, metrics: CompetitionMetrics) -> None:
    if not metrics.is_determinable:
        logger.warning(
            "Заказчик {} неопределим: нет успешных анализов | всего={}, пропущено={}",
            customer_inn,
            metrics.total_historical,
            metrics.total_skipped,
        )
        return

    status = "ИНТЕРЕСНЫЙ" if metrics.is_interesting else "не интересный"
    logger.info(
        "Заказчик {} → {} | низкая={}/{}, доля={:.0%}, пропущено={}",
        customer_inn,
        status,
        metrics.low_competition_count,
        metrics.total_analyzed,
        metrics.competition_ratio or 0,
        metrics.total_skipped,
    )
