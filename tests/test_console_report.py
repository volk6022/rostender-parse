"""Tests for src.reporter.console_report."""

from __future__ import annotations

from tests.conftest import MockRow

from src.reporter.console_report import log_console_summary, print_console_report


# ── Fixtures (inline) ────────────────────────────────────────────────────────


def _make_interesting_row(**overrides) -> MockRow:
    """Create a MockRow representing an interesting result."""
    defaults = {
        "tender_title": "Поставка оборудования для ЦОД",
        "tender_url": "https://rostender.info/tender/12345",
        "tender_price": 5_000_000.0,
        "customer_name": 'ООО "Ромашка"',
        "customer_inn": "1234567890",
        "total_historical": 10,
        "total_analyzed": 8,
        "low_competition_count": 6,
        "competition_ratio": 0.75,
        "source": "primary",
    }
    defaults.update(overrides)
    return MockRow(defaults)


def _make_customer_row(**overrides) -> MockRow:
    defaults = {
        "inn": "1234567890",
        "name": 'ООО "Ромашка"',
        "status": "analyzed",
    }
    defaults.update(overrides)
    return MockRow(defaults)


def _make_result_row(**overrides) -> MockRow:
    defaults = {
        "customer_inn": "1234567890",
        "total_historical": 10,
        "total_analyzed": 8,
    }
    defaults.update(overrides)
    return MockRow(defaults)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPrintConsoleReport:
    """Tests for print_console_report function."""

    def test_empty_interesting(self, capsys) -> None:
        """When no interesting results, should print warning."""
        print_console_report(
            interesting_results=[],
            all_results=[_make_result_row()],
            all_customers=[_make_customer_row()],
        )
        output = capsys.readouterr().out

        assert "ОТЧЁТ: Rostender Parser" in output
        assert "Интересных тендеров:        0" in output
        assert "Интересных тендеров не найдено" in output

    def test_all_empty(self, capsys) -> None:
        """When everything is empty, should still produce a report."""
        print_console_report(
            interesting_results=[],
            all_results=[],
            all_customers=[],
        )
        output = capsys.readouterr().out

        assert "Всего заказчиков в базе:     0" in output
        assert "Всего проанализировано:      0" in output
        assert "Интересных тендеров:        0" in output

    def test_with_interesting_results(self, capsys) -> None:
        """Should print details of interesting tenders."""
        rows = [_make_interesting_row()]
        print_console_report(
            interesting_results=rows,
            all_results=[_make_result_row()],
            all_customers=[_make_customer_row()],
        )
        output = capsys.readouterr().out

        assert "Интересных тендеров:        1" in output
        assert "ИНТЕРЕСНЫЕ ТЕНДЕРЫ" in output
        assert "Поставка оборудования для ЦОД" in output
        assert "1234567890" in output
        assert 'ООО "Ромашка"' in output
        assert "5,000,000" in output
        assert "6/8 тендеров с низкой конкуренцией" in output
        assert "75%" in output
        assert "Основной" in output

    def test_extended_source_label(self, capsys) -> None:
        """Extended source should display 'Расширенный'."""
        rows = [_make_interesting_row(source="extended")]
        print_console_report(
            interesting_results=rows,
            all_results=[_make_result_row()],
            all_customers=[_make_customer_row()],
        )
        output = capsys.readouterr().out
        assert "Расширенный" in output

    def test_no_price_no_url(self, capsys) -> None:
        """When price is 0/None and URL is empty, those lines are skipped."""
        rows = [_make_interesting_row(tender_price=0, tender_url="")]
        print_console_report(
            interesting_results=rows,
            all_results=[_make_result_row()],
            all_customers=[_make_customer_row()],
        )
        output = capsys.readouterr().out
        # price line should not appear (falsy 0)
        assert "Цена:" not in output
        assert "URL:" not in output

    def test_none_ratio(self, capsys) -> None:
        """When competition_ratio is None, 'Доля' line should not appear."""
        rows = [_make_interesting_row(competition_ratio=None)]
        print_console_report(
            interesting_results=rows,
            all_results=[_make_result_row()],
            all_customers=[_make_customer_row()],
        )
        output = capsys.readouterr().out
        assert "Доля:" not in output

    def test_long_title_truncated(self, capsys) -> None:
        """Titles longer than 60 chars should be truncated with '...'."""
        long_title = "А" * 80
        rows = [_make_interesting_row(tender_title=long_title)]
        print_console_report(
            interesting_results=rows,
            all_results=[_make_result_row()],
            all_customers=[_make_customer_row()],
        )
        output = capsys.readouterr().out
        assert "..." in output
        # First 60 chars should be present
        assert "А" * 60 in output

    def test_multiple_results(self, capsys) -> None:
        """Multiple interesting results should be numbered sequentially."""
        rows = [
            _make_interesting_row(tender_title="Тендер первый", customer_inn="111"),
            _make_interesting_row(tender_title="Тендер второй", customer_inn="222"),
            _make_interesting_row(tender_title="Тендер третий", customer_inn="333"),
        ]
        print_console_report(
            interesting_results=rows,
            all_results=[_make_result_row()],
            all_customers=[_make_customer_row()],
        )
        output = capsys.readouterr().out
        assert "1. Тендер первый" in output
        assert "2. Тендер второй" in output
        assert "3. Тендер третий" in output

    def test_customer_name_fallback_to_inn(self, capsys) -> None:
        """When customer_name is None, should fall back to customer_inn."""
        rows = [_make_interesting_row(customer_name=None, customer_inn="9876543210")]
        print_console_report(
            interesting_results=rows,
            all_results=[_make_result_row()],
            all_customers=[_make_customer_row()],
        )
        output = capsys.readouterr().out
        assert "Заказчик: 9876543210" in output


class TestLogConsoleSummary:
    """Tests for log_console_summary function."""

    def test_logs_summary(self, capfd) -> None:
        """Should log summary without raising."""
        # Just verify it doesn't crash — loguru writes to stderr
        log_console_summary(total_customers=10, total_interesting=3)

    def test_logs_zero_values(self) -> None:
        """Should handle zero values."""
        log_console_summary(total_customers=0, total_interesting=0)
