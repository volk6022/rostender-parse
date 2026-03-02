"""Tests for src.main — CLI argument parsing and dispatcher logic."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import _add_common_args, _parse_args


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse(argv: list[str]):
    """Call _parse_args with patched sys.argv."""
    with patch.object(sys, "argv", ["rostender"] + argv):
        return _parse_args()


# ── TestParseArgs ────────────────────────────────────────────────────────────


class TestParseArgsDefaults:
    """Tests for default argument values."""

    def test_no_args_defaults_to_run(self) -> None:
        args = _parse([])
        assert args.command == "run"

    def test_explicit_run(self) -> None:
        args = _parse(["run"])
        assert args.command == "run"

    def test_search_active_command(self) -> None:
        args = _parse(["search-active"])
        assert args.command == "search-active"

    def test_analyze_history_command(self) -> None:
        args = _parse(["analyze-history"])
        assert args.command == "analyze-history"

    def test_extended_search_command(self) -> None:
        args = _parse(["extended-search"])
        assert args.command == "extended-search"

    def test_report_command(self) -> None:
        args = _parse(["report"])
        assert args.command == "report"

    def test_default_keywords_none(self) -> None:
        args = _parse([])
        assert args.keywords is None

    def test_default_min_price_none(self) -> None:
        args = _parse([])
        assert args.min_price is None

    def test_default_days_back(self) -> None:
        args = _parse([])
        assert args.days_back == 7

    def test_default_dry_run_false(self) -> None:
        args = _parse([])
        assert args.dry_run is False

    def test_default_headless_true(self) -> None:
        args = _parse([])
        assert args.headless is True

    def test_default_no_headless_false(self) -> None:
        args = _parse([])
        assert args.no_headless is False


class TestParseArgsOverrides:
    """Tests for CLI argument overrides."""

    def test_keywords(self) -> None:
        args = _parse(["-k", "word1", "word2"])
        assert args.keywords == ["word1", "word2"]

    def test_min_price(self) -> None:
        args = _parse(["-p", "5000000"])
        assert args.min_price == 5000000

    def test_min_price_related(self) -> None:
        args = _parse(["--min-price-related", "1000000"])
        assert args.min_price_related == 1000000

    def test_min_price_historical(self) -> None:
        args = _parse(["--min-price-historical", "500000"])
        assert args.min_price_historical == 500000

    def test_history_limit(self) -> None:
        args = _parse(["-l", "20"])
        assert args.history_limit == 20

    def test_max_participants(self) -> None:
        args = _parse(["-m", "5"])
        assert args.max_participants == 5

    def test_ratio_threshold(self) -> None:
        args = _parse(["-r", "0.5"])
        assert args.ratio_threshold == 0.5

    def test_date_from(self) -> None:
        args = _parse(["--date-from", "01.01.2025"])
        assert args.date_from == "01.01.2025"

    def test_date_to(self) -> None:
        args = _parse(["--date-to", "31.12.2025"])
        assert args.date_to == "31.12.2025"

    def test_days_back_custom(self) -> None:
        args = _parse(["-d", "30"])
        assert args.days_back == 30

    def test_dry_run(self) -> None:
        args = _parse(["--dry-run"])
        assert args.dry_run is True

    def test_no_headless_sets_headless_false(self) -> None:
        args = _parse(["--no-headless"])
        assert args.no_headless is True
        assert args.headless is False


class TestParseArgsSubcommandOverrides:
    """Tests that subcommand-level args work."""

    def test_search_active_with_keywords(self) -> None:
        args = _parse(["search-active", "-k", "IT", "сервер"])
        assert args.command == "search-active"
        assert args.keywords == ["IT", "сервер"]

    def test_run_with_min_price(self) -> None:
        args = _parse(["run", "--min-price", "999"])
        assert args.command == "run"
        assert args.min_price == 999

    def test_report_with_dry_run(self) -> None:
        args = _parse(["report", "--dry-run"])
        assert args.command == "report"
        assert args.dry_run is True

    def test_analyze_history_no_headless(self) -> None:
        args = _parse(["analyze-history", "--no-headless"])
        assert args.command == "analyze-history"
        assert args.headless is False

    def test_extended_search_with_days_back(self) -> None:
        args = _parse(["extended-search", "-d", "14"])
        assert args.command == "extended-search"
        assert args.days_back == 14


# ── Tests for _configure_logging ──────────────────────────────────────────────


class TestConfigureLogging:
    """Tests for _configure_logging()."""

    def test_removes_default_handler(self) -> None:
        """Removes all existing loguru handlers before adding new ones."""
        from src.main import _configure_logging

        with patch("src.main.logger") as mock_logger:
            _configure_logging()

        mock_logger.remove.assert_called_once()

    def test_adds_stderr_and_file_handlers(self) -> None:
        """Adds both stderr and file handlers."""
        from src.main import _configure_logging

        with patch("src.main.logger") as mock_logger:
            _configure_logging()

        assert mock_logger.add.call_count == 2
        # First call: stderr handler
        first_call = mock_logger.add.call_args_list[0]
        assert first_call.args[0] is sys.stderr
        assert first_call.kwargs["level"] == "INFO"
        # Second call: file handler
        second_call = mock_logger.add.call_args_list[1]
        assert second_call.kwargs["level"] == "DEBUG"
        assert second_call.kwargs["rotation"] == "5 MB"


# ── Tests for _ensure_dirs ────────────────────────────────────────────────────


class TestEnsureDirs:
    """Tests for _ensure_dirs()."""

    def test_creates_all_required_directories(self, tmp_path) -> None:
        """Creates DATA_DIR, DOWNLOADS_DIR, and REPORTS_DIR."""
        data = tmp_path / "data"
        downloads = tmp_path / "downloads"
        reports = tmp_path / "reports"

        with (
            patch("src.main.DATA_DIR", data),
            patch("src.main.DOWNLOADS_DIR", downloads),
            patch("src.main.REPORTS_DIR", reports),
        ):
            from src.main import _ensure_dirs

            _ensure_dirs()

        assert data.exists()
        assert downloads.exists()
        assert reports.exists()

    def test_idempotent(self, tmp_path) -> None:
        """Can be called multiple times without error."""
        data = tmp_path / "data"
        downloads = tmp_path / "downloads"
        reports = tmp_path / "reports"

        with (
            patch("src.main.DATA_DIR", data),
            patch("src.main.DOWNLOADS_DIR", downloads),
            patch("src.main.REPORTS_DIR", reports),
        ):
            from src.main import _ensure_dirs

            _ensure_dirs()
            _ensure_dirs()  # Should not raise


# ── Tests for run() async dispatcher ──────────────────────────────────────────


class TestRun:
    """Tests for run() async dispatcher."""

    @pytest.mark.asyncio
    async def test_dry_run_exits_early(self) -> None:
        """--dry-run logs parameters and returns without running stages."""
        with (
            patch.object(sys, "argv", ["rostender", "--dry-run"]),
            patch("src.main._configure_logging"),
            patch("src.main._ensure_dirs"),
            patch("src.main.validate_config") as mock_validate,
            patch("src.main.init_db", new_callable=AsyncMock) as mock_init_db,
        ):
            from src.main import run

            await run()

        # validate_config and init_db should NOT be called in dry-run
        mock_validate.assert_not_called()
        mock_init_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_command_calls_all_stages(self) -> None:
        """'run' command calls all 4 stages with a single browser session."""
        mock_page = AsyncMock()
        mock_browser = AsyncMock()

        # create_browser returns async CM yielding mock_browser
        mock_create_browser = MagicMock()
        mock_browser_cm = AsyncMock()
        mock_browser_cm.__aenter__ = AsyncMock(return_value=mock_browser)
        mock_browser_cm.__aexit__ = AsyncMock(return_value=False)
        mock_create_browser.return_value = mock_browser_cm

        # create_page returns async CM yielding mock_page
        mock_create_page = MagicMock()
        mock_page_cm = AsyncMock()
        mock_page_cm.__aenter__ = AsyncMock(return_value=mock_page)
        mock_page_cm.__aexit__ = AsyncMock(return_value=False)
        mock_create_page.return_value = mock_page_cm

        with (
            patch.object(sys, "argv", ["rostender", "run"]),
            patch("src.main._configure_logging"),
            patch("src.main._ensure_dirs"),
            patch("src.main.validate_config"),
            patch("src.main.init_db", new_callable=AsyncMock),
            patch("src.main.create_browser", mock_create_browser),
            patch("src.main.create_page", mock_create_page),
            patch("src.main.login", new_callable=AsyncMock) as mock_login,
            patch("src.main.run_search_active", new_callable=AsyncMock) as mock_s1,
            patch("src.main.run_analyze_history", new_callable=AsyncMock) as mock_s2,
            patch("src.main.run_extended_search", new_callable=AsyncMock) as mock_s3,
            patch("src.main.run_report", new_callable=AsyncMock) as mock_s4,
        ):
            from src.main import run

            await run()

        mock_login.assert_called_once_with(mock_page)
        mock_s1.assert_called_once()
        mock_s2.assert_called_once()
        mock_s3.assert_called_once()
        mock_s4.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_command_no_browser(self) -> None:
        """'report' command does not create a browser."""
        with (
            patch.object(sys, "argv", ["rostender", "report"]),
            patch("src.main._configure_logging"),
            patch("src.main._ensure_dirs"),
            patch("src.main.validate_config"),
            patch("src.main.init_db", new_callable=AsyncMock),
            patch("src.main.create_browser") as mock_browser,
            patch("src.main.run_report", new_callable=AsyncMock) as mock_report,
        ):
            from src.main import run

            await run()

        mock_browser.assert_not_called()
        mock_report.assert_called_once()

    @pytest.mark.asyncio
    async def test_individual_stage_gets_own_browser(self) -> None:
        """Individual stages (search-active, etc.) create their own browser session."""
        mock_page = AsyncMock()
        mock_browser = AsyncMock()

        mock_create_browser = MagicMock()
        mock_browser_cm = AsyncMock()
        mock_browser_cm.__aenter__ = AsyncMock(return_value=mock_browser)
        mock_browser_cm.__aexit__ = AsyncMock(return_value=False)
        mock_create_browser.return_value = mock_browser_cm

        mock_create_page = MagicMock()
        mock_page_cm = AsyncMock()
        mock_page_cm.__aenter__ = AsyncMock(return_value=mock_page)
        mock_page_cm.__aexit__ = AsyncMock(return_value=False)
        mock_create_page.return_value = mock_page_cm

        with (
            patch.object(sys, "argv", ["rostender", "search-active"]),
            patch("src.main._configure_logging"),
            patch("src.main._ensure_dirs"),
            patch("src.main.validate_config"),
            patch("src.main.init_db", new_callable=AsyncMock),
            patch("src.main.create_browser", mock_create_browser),
            patch("src.main.create_page", mock_create_page),
            patch("src.main.login", new_callable=AsyncMock) as mock_login,
            patch("src.main.run_search_active", new_callable=AsyncMock) as mock_s1,
        ):
            from src.main import run

            await run()

        mock_login.assert_called_once()
        mock_s1.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_config_called_before_stages(self) -> None:
        """validate_config is called before any stage execution."""
        call_order: list[str] = []

        async def mock_init_db():
            call_order.append("init_db")

        async def mock_report(_params):
            call_order.append("report")

        def mock_validate():
            call_order.append("validate")

        with (
            patch.object(sys, "argv", ["rostender", "report"]),
            patch("src.main._configure_logging"),
            patch("src.main._ensure_dirs"),
            patch("src.main.validate_config", side_effect=mock_validate),
            patch("src.main.init_db", side_effect=mock_init_db),
            patch("src.main.run_report", side_effect=mock_report),
        ):
            from src.main import run

            await run()

        assert call_order == ["validate", "init_db", "report"]

    @pytest.mark.asyncio
    async def test_config_error_propagates(self) -> None:
        """ConfigError from validate_config propagates up."""
        from src.config import ConfigError

        with (
            patch.object(sys, "argv", ["rostender", "report"]),
            patch("src.main._configure_logging"),
            patch("src.main._ensure_dirs"),
            patch(
                "src.main.validate_config",
                side_effect=ConfigError("missing config"),
            ),
        ):
            from src.main import run

            with pytest.raises(ConfigError, match="missing config"):
                await run()


# ── Tests for main() ─────────────────────────────────────────────────────────


class TestMain:
    """Tests for main() sync wrapper."""

    def test_calls_asyncio_run(self) -> None:
        """main() calls asyncio.run(run())."""
        # Use MagicMock for `run` to avoid AsyncMock creating an unawaited coroutine
        # (asyncio.run is also mocked, so the coroutine would never be awaited)
        mock_run_fn = MagicMock(return_value="fake_coroutine")

        with (
            patch("src.main.asyncio.run") as mock_asyncio_run,
            patch("src.main.run", mock_run_fn),
            patch("sys.stdout") as mock_stdout,
            patch("sys.stderr") as mock_stderr,
        ):
            mock_stdout.encoding = "utf-8"
            mock_stderr.encoding = "utf-8"

            from src.main import main

            main()

        mock_asyncio_run.assert_called_once_with("fake_coroutine")

    def test_reconfigures_stdout_for_non_utf8(self) -> None:
        """Reconfigures stdout to UTF-8 when encoding is not utf-8."""
        mock_stdout = MagicMock()
        mock_stdout.encoding = "cp1252"
        mock_stderr = MagicMock()
        mock_stderr.encoding = "utf-8"

        # Use MagicMock for `run` to avoid AsyncMock creating an unawaited coroutine
        mock_run_fn = MagicMock(return_value="fake_coroutine")

        with (
            patch("src.main.asyncio.run"),
            patch("src.main.run", mock_run_fn),
            patch("src.main.sys.stdout", mock_stdout),
            patch("src.main.sys.stderr", mock_stderr),
        ):
            from src.main import main

            main()

        mock_stdout.reconfigure.assert_called_once_with(
            encoding="utf-8", errors="replace"
        )
