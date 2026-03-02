"""Tests for src.scraper.source_links."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.scraper.source_links import (
    extract_source_urls,
    get_source_url,
    parse_source_urls,
)


class TestExtractSourceUrls:
    @pytest.mark.asyncio
    async def test_extracts_eis_link(self):
        page = AsyncMock()
        link = AsyncMock()
        link.get_attribute = AsyncMock(
            return_value="https://zakupki.gov.ru/epz/order/notice/ok504/view/common-info.html?regNumber=123"
        )
        page.query_selector_all = AsyncMock(return_value=[link])

        result = await extract_source_urls(page)
        assert (
            result
            == "eis:https://zakupki.gov.ru/epz/order/notice/ok504/view/common-info.html?regNumber=123"
        )

    @pytest.mark.asyncio
    async def test_returns_none_if_no_source_links(self):
        page = AsyncMock()
        link = AsyncMock()
        link.get_attribute = AsyncMock(return_value="https://example.com/other")
        page.query_selector_all = AsyncMock(return_value=[link])

        result = await extract_source_urls(page)
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_exception(self):
        page = AsyncMock()
        page.query_selector_all = AsyncMock(side_effect=Exception("DOM error"))

        result = await extract_source_urls(page)
        assert result is None


class TestGetSourceUrl:
    def test_gets_existing_source(self):
        source_urls = "eis:https://zakupki.gov.ru/1,gpb:https://etpgpb.ru/2"
        assert get_source_url(source_urls, "eis") == "https://zakupki.gov.ru/1"
        assert get_source_url(source_urls, "gpb") == "https://etpgpb.ru/2"

    def test_returns_none_for_missing_source(self):
        source_urls = "eis:https://zakupki.gov.ru/1"
        assert get_source_url(source_urls, "gpb") is None

    def test_returns_none_for_empty_input(self):
        assert get_source_url(None, "eis") is None
        assert get_source_url("", "eis") is None


class TestParseSourceUrls:
    def test_parses_multiple_urls(self):
        source_urls = "eis:https://zakupki.gov.ru/1,gpb:https://etpgpb.ru/2"
        result = parse_source_urls(source_urls)
        assert result == {
            "eis": "https://zakupki.gov.ru/1",
            "gpb": "https://etpgpb.ru/2",
        }

    def test_parses_single_url(self):
        source_urls = "eis:https://zakupki.gov.ru/1"
        result = parse_source_urls(source_urls)
        assert result == {"eis": "https://zakupki.gov.ru/1"}

    def test_returns_empty_dict_for_invalid_input(self):
        assert parse_source_urls(None) == {}
        assert parse_source_urls("") == {}
