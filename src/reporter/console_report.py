"""Вывод отчёта в консоль."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from loguru import logger


def print_console_report(
    interesting_results: Sequence[Any],
    all_results: Sequence[Any],
    all_customers: Sequence[Any],
) -> None:
    total_interesting = len(interesting_results)
    total_results = len(all_results)
    total_customers = len(all_customers)

    print("\n" + "=" * 80)
    print("ОТЧЁТ: Rostender Parser")
    print("=" * 80)

    print(f"\n📊 СВОДКА:")
    print(f"   Всего заказчиков в базе:     {total_customers}")
    print(f"   Всего проанализировано:      {total_results}")
    print(f"   Интересных тендеров:        {total_interesting}")

    if not interesting_results:
        print("\n⚠️  Интересных тендеров не найдено.")
        return

    print("\n" + "-" * 80)
    print("📋 ИНТЕРЕСНЫЕ ТЕНДЕРЫ (исторически низкая конкуренция):")
    print("-" * 80)

    for i, row in enumerate(interesting_results, 1):
        title = row["tender_title"] or "Без названия"
        url = row["tender_url"] or ""
        price = row["tender_price"]
        customer_name = row["customer_name"] or row["customer_inn"]
        customer_inn = row["customer_inn"]
        total_hist = row["total_historical"]
        total_analyzed = row["total_analyzed"]
        low_comp = row["low_competition_count"]
        ratio = row["competition_ratio"]
        source = row["source"]

        source_label = "📌 Основной" if source == "primary" else "🔍 Расширенный"

        print(f"\n{i}. {title[:60]}{'...' if len(title) > 60 else ''}")
        print(f"   Заказчик: {customer_name}")
        print(f"   ИНН:      {customer_inn}")
        if price:
            print(f"   Цена:     {price:,.0f} ₽")
        if url:
            print(f"   URL:      {url}")
        print(
            f"   Анализ:   {low_comp}/{total_analyzed} тендеров с низкой конкуренцией"
        )
        if ratio is not None:
            print(f"   Доля:     {ratio:.0%}")
        print(f"   {source_label}")

    print("\n" + "=" * 80)


def log_console_summary(
    total_customers: int,
    total_interesting: int,
) -> None:
    logger.info(
        "Отчёт сформирован: заказчиков={}, интересных тендеров={}",
        total_customers,
        total_interesting,
    )
