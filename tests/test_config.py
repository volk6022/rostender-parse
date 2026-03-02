"""Tests for src.config — configuration loading and validation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.config import (
    BASE_URL,
    ConfigError,
    DATA_DIR,
    DB_PATH,
    DEFAULT_TIMEOUT,
    DOWNLOADS_DIR,
    POLITE_DELAY,
    PROJECT_ROOT,
    REPORTS_DIR,
    SELECTORS,
    validate_config,
)


class TestPaths:
    """Tests for computed paths."""

    def test_project_root_exists(self) -> None:
        assert PROJECT_ROOT.exists()

    def test_data_dir_under_root(self) -> None:
        assert DATA_DIR == PROJECT_ROOT / "data"

    def test_downloads_dir_under_root(self) -> None:
        assert DOWNLOADS_DIR == PROJECT_ROOT / "downloads"

    def test_reports_dir_under_root(self) -> None:
        assert REPORTS_DIR == PROJECT_ROOT / "reports"

    def test_db_path_under_data(self) -> None:
        assert DB_PATH == DATA_DIR / "rostender.db"


class TestConstants:
    """Tests for hardcoded constants."""

    def test_base_url(self) -> None:
        assert BASE_URL == "https://rostender.info"

    def test_default_timeout_positive(self) -> None:
        assert DEFAULT_TIMEOUT > 0

    def test_polite_delay_positive(self) -> None:
        assert POLITE_DELAY > 0


class TestSelectors:
    """Tests for CSS selectors dict."""

    def test_selectors_is_dict(self) -> None:
        assert isinstance(SELECTORS, dict)

    def test_required_keys_present(self) -> None:
        required = [
            "login_username",
            "login_password",
            "login_button",
            "logged_in_marker",
            "search_button",
            "tender_card",
            "inn_button",
            "eis_link",
        ]
        for key in required:
            assert key in SELECTORS, f"Missing selector: {key}"

    def test_all_values_are_strings(self) -> None:
        for key, value in SELECTORS.items():
            assert isinstance(value, str), f"Selector {key} is not str: {type(value)}"

    def test_all_values_non_empty(self) -> None:
        for key, value in SELECTORS.items():
            assert value.strip(), f"Selector {key} is empty"


class TestValidateConfig:
    """Tests for validate_config() function."""

    def test_validate_config_succeeds_with_valid_config(self) -> None:
        """Should not raise when config.yaml exists and has credentials."""
        # This test runs in an environment where config.yaml exists
        # (CI or dev machine with valid config)
        try:
            validate_config()
        except ConfigError:
            pytest.skip("config.yaml not present or missing credentials")

    def test_validate_config_raises_on_missing_file(self) -> None:
        """Should raise ConfigError when config.yaml doesn't exist."""
        with patch("src.config._CONFIG_PATH") as mock_path:
            mock_path.exists.return_value = False
            with pytest.raises(ConfigError, match="Файл конфигурации не найден"):
                validate_config()

    def test_validate_config_raises_on_empty_credentials(self) -> None:
        """Should raise ConfigError when login/password are empty."""
        with patch("src.config._CONFIG_PATH") as mock_path:
            mock_path.exists.return_value = True
            with (
                patch("src.config.ROSTENDER_LOGIN", ""),
                patch("src.config.ROSTENDER_PASSWORD", ""),
            ):
                with pytest.raises(ConfigError, match="обязательны"):
                    validate_config()

    def test_validate_config_raises_on_missing_login(self) -> None:
        """Should raise ConfigError when only login is empty."""
        with patch("src.config._CONFIG_PATH") as mock_path:
            mock_path.exists.return_value = True
            with (
                patch("src.config.ROSTENDER_LOGIN", ""),
                patch("src.config.ROSTENDER_PASSWORD", "somepass"),
            ):
                with pytest.raises(ConfigError):
                    validate_config()

    def test_validate_config_raises_on_missing_password(self) -> None:
        """Should raise ConfigError when only password is empty."""
        with patch("src.config._CONFIG_PATH") as mock_path:
            mock_path.exists.return_value = True
            with (
                patch("src.config.ROSTENDER_LOGIN", "someuser"),
                patch("src.config.ROSTENDER_PASSWORD", ""),
            ):
                with pytest.raises(ConfigError):
                    validate_config()


class TestConfigError:
    """Tests for ConfigError exception class."""

    def test_is_exception(self) -> None:
        assert issubclass(ConfigError, Exception)

    def test_message_preserved(self) -> None:
        err = ConfigError("test message")
        assert str(err) == "test message"
