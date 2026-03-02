"""Tests for src.scraper.eis_fallback — EIS (zakupki.gov.ru) fallback logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Tests for extract_inn_from_eis ───────────────────────────────────────────


class TestExtractInnFromEis:
    """Tests for extract_inn_from_eis() — INN extraction from EIS page."""

    @pytest.mark.asyncio
    async def test_finds_inn_in_page_content_regex(self) -> None:
        """Finds INN via regex in page HTML content."""
        page = AsyncMock()
        page.content = AsyncMock(return_value="<div>ИНН: 1234567890</div>")

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import extract_inn_from_eis

            result = await extract_inn_from_eis(page, "https://zakupki.gov.ru/123")

        assert result == "1234567890"

    @pytest.mark.asyncio
    async def test_finds_12_digit_inn(self) -> None:
        """Finds 12-digit INN (individual entrepreneur)."""
        page = AsyncMock()
        page.content = AsyncMock(return_value="<span>ИНН 123456789012</span>")

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import extract_inn_from_eis

            result = await extract_inn_from_eis(page, "https://eis/test")

        assert result == "123456789012"

    @pytest.mark.asyncio
    async def test_finds_inn_in_data_attribute(self) -> None:
        """Falls back to data-inn attribute when regex doesn't match."""
        page = AsyncMock()
        page.content = AsyncMock(return_value="<div>no INN here</div>")

        inn_el = AsyncMock()
        inn_el.get_attribute = AsyncMock(
            side_effect=lambda attr: "9876543210" if attr == "data-inn" else None
        )

        page.query_selector = AsyncMock(
            side_effect=lambda sel: inn_el if "data-inn" in sel else None
        )

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import extract_inn_from_eis

            result = await extract_inn_from_eis(page, "https://eis/test")

        assert result == "9876543210"

    @pytest.mark.asyncio
    async def test_finds_inn_in_customer_block(self) -> None:
        """Falls back to customer block text when data-attr not found."""
        page = AsyncMock()
        page.content = AsyncMock(return_value="<div>no match</div>")

        customer_block = AsyncMock()
        customer_block.inner_text = AsyncMock(
            return_value="Заказчик ООО Рога\nКод: 5551234567"
        )

        def mock_query_selector(sel: str):
            if "customerInfo" in sel:
                return customer_block
            return None

        page.query_selector = AsyncMock(side_effect=mock_query_selector)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import extract_inn_from_eis

            result = await extract_inn_from_eis(page, "https://eis/test")

        assert result == "5551234567"

    @pytest.mark.asyncio
    async def test_returns_none_when_inn_not_found(self) -> None:
        """Returns None when no INN found anywhere on the page."""
        page = AsyncMock()
        page.content = AsyncMock(return_value="<div>nothing relevant</div>")
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import extract_inn_from_eis

            result = await extract_inn_from_eis(page, "https://eis/test")

        assert result is None


# ── Tests for search_historical_tenders_on_eis ───────────────────────────────


class TestSearchHistoricalTendersOnEis:
    """Tests for search_historical_tenders_on_eis()."""

    @pytest.mark.asyncio
    async def test_no_results_container(self) -> None:
        """Returns empty list when results container not found."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import search_historical_tenders_on_eis

            result = await search_historical_tenders_on_eis(page, "1234567890")

        assert result == []

    @pytest.mark.asyncio
    async def test_parses_tender_cards(self) -> None:
        """Parses tender cards from search results."""
        page = AsyncMock()

        # Create a mock card with link, title, price
        link_el = AsyncMock()
        link_el.get_attribute = AsyncMock(return_value="/epz/order/view?id=12345")

        title_el = AsyncMock()
        title_el.inner_text = AsyncMock(return_value="  Поставка оборудования  ")

        price_el = AsyncMock()
        price_el.inner_text = AsyncMock(return_value="5 000 000,50 ₽")

        card = AsyncMock()

        async def card_query_selector(sel: str):
            if "order/view" in sel:
                return link_el
            if "title" in sel:
                return title_el
            if "price" in sel:
                return price_el
            return None

        card.query_selector = AsyncMock(side_effect=card_query_selector)

        results_container = AsyncMock()
        results_container.query_selector_all = AsyncMock(return_value=[card])

        page.query_selector = AsyncMock(return_value=results_container)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.MIN_PRICE_HISTORICAL", 1_000_000),
        ):
            from src.scraper.eis_fallback import search_historical_tenders_on_eis

            result = await search_historical_tenders_on_eis(page, "1234567890")

        assert len(result) == 1
        assert result[0]["tender_id"] == "12345"
        assert result[0]["title"] == "Поставка оборудования"
        assert result[0]["price"] == 5000000.50

    @pytest.mark.asyncio
    async def test_skips_cards_without_link(self) -> None:
        """Cards without a[href*='order/view'] are skipped."""
        page = AsyncMock()

        card = AsyncMock()
        card.query_selector = AsyncMock(return_value=None)  # no link element

        results_container = AsyncMock()
        results_container.query_selector_all = AsyncMock(return_value=[card])

        page.query_selector = AsyncMock(return_value=results_container)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import search_historical_tenders_on_eis

            result = await search_historical_tenders_on_eis(page, "1234567890")

        assert result == []

    @pytest.mark.asyncio
    async def test_skips_tender_below_min_price(self) -> None:
        """Tenders with price below MIN_PRICE_HISTORICAL are filtered out."""
        page = AsyncMock()

        link_el = AsyncMock()
        link_el.get_attribute = AsyncMock(return_value="/epz/order/view?id=99")

        title_el = AsyncMock()
        title_el.inner_text = AsyncMock(return_value="Cheap tender")

        price_el = AsyncMock()
        price_el.inner_text = AsyncMock(return_value="500 000 ₽")

        card = AsyncMock()

        async def card_qs(sel: str):
            if "order/view" in sel:
                return link_el
            if "title" in sel:
                return title_el
            if "price" in sel:
                return price_el
            return None

        card.query_selector = AsyncMock(side_effect=card_qs)

        results_container = AsyncMock()
        results_container.query_selector_all = AsyncMock(return_value=[card])

        page.query_selector = AsyncMock(return_value=results_container)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.MIN_PRICE_HISTORICAL", 1_000_000),
        ):
            from src.scraper.eis_fallback import search_historical_tenders_on_eis

            result = await search_historical_tenders_on_eis(page, "1234567890")

        assert result == []

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self) -> None:
        """Only processes up to `limit` tender cards."""
        page = AsyncMock()

        def make_card(tid: str):
            link_el = AsyncMock()
            link_el.get_attribute = AsyncMock(return_value=f"/epz/order/view?id={tid}")
            title_el = AsyncMock()
            title_el.inner_text = AsyncMock(return_value=f"Tender {tid}")
            card = AsyncMock()

            async def card_qs(sel: str):
                if "order/view" in sel:
                    return link_el
                if "title" in sel:
                    return title_el
                return None  # no price → price=None → not filtered

            card.query_selector = AsyncMock(side_effect=card_qs)
            return card

        cards = [make_card(str(i)) for i in range(10)]
        results_container = AsyncMock()
        results_container.query_selector_all = AsyncMock(return_value=cards)

        page.query_selector = AsyncMock(return_value=results_container)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import search_historical_tenders_on_eis

            result = await search_historical_tenders_on_eis(page, "1234567890", limit=3)

        assert len(result) <= 3

    @pytest.mark.asyncio
    async def test_card_parse_exception_continues(self) -> None:
        """Exception parsing one card doesn't stop processing others."""
        page = AsyncMock()

        # First card raises, second card succeeds
        bad_card = AsyncMock()
        bad_card.query_selector = AsyncMock(side_effect=Exception("parse error"))

        link_el = AsyncMock()
        link_el.get_attribute = AsyncMock(return_value="/epz/order/view?id=2")
        title_el = AsyncMock()
        title_el.inner_text = AsyncMock(return_value="Good tender")
        good_card = AsyncMock()

        async def good_qs(sel: str):
            if "order/view" in sel:
                return link_el
            if "title" in sel:
                return title_el
            return None

        good_card.query_selector = AsyncMock(side_effect=good_qs)

        results_container = AsyncMock()
        results_container.query_selector_all = AsyncMock(
            return_value=[bad_card, good_card]
        )

        page.query_selector = AsyncMock(return_value=results_container)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import search_historical_tenders_on_eis

            result = await search_historical_tenders_on_eis(page, "1234567890")

        assert len(result) == 1
        assert result[0]["tender_id"] == "2"

    @pytest.mark.asyncio
    async def test_absolute_href_not_prefixed(self) -> None:
        """When href is already absolute, don't prefix with EIS_BASE_URL."""
        page = AsyncMock()

        link_el = AsyncMock()
        link_el.get_attribute = AsyncMock(
            return_value="https://zakupki.gov.ru/epz/order/view?id=42"
        )
        title_el = AsyncMock()
        title_el.inner_text = AsyncMock(return_value="Tender")

        card = AsyncMock()

        async def card_qs(sel: str):
            if "order/view" in sel:
                return link_el
            if "title" in sel:
                return title_el
            return None

        card.query_selector = AsyncMock(side_effect=card_qs)

        results_container = AsyncMock()
        results_container.query_selector_all = AsyncMock(return_value=[card])
        page.query_selector = AsyncMock(return_value=results_container)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import search_historical_tenders_on_eis

            result = await search_historical_tenders_on_eis(page, "1234567890")

        assert result[0]["eis_url"] == "https://zakupki.gov.ru/epz/order/view?id=42"


# ── Tests for get_protocol_link_from_eis ─────────────────────────────────────


class TestGetProtocolLinkFromEis:
    """Tests for get_protocol_link_from_eis()."""

    @pytest.mark.asyncio
    async def test_finds_protocol_link(self) -> None:
        """Returns full URL when protocol link found."""
        page = AsyncMock()

        link = AsyncMock()
        link.get_attribute = AsyncMock(return_value="/epz/order/protocol/view?id=100")

        page.query_selector_all = AsyncMock(return_value=[link])

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import get_protocol_link_from_eis

            result = await get_protocol_link_from_eis(page, "https://eis/tender")

        assert result == "https://zakupki.gov.ru/epz/order/protocol/view?id=100"

    @pytest.mark.asyncio
    async def test_returns_absolute_url_as_is(self) -> None:
        """Absolute protocol URL returned without prefix."""
        page = AsyncMock()

        link = AsyncMock()
        link.get_attribute = AsyncMock(return_value="https://other.site/protocol/123")

        page.query_selector_all = AsyncMock(return_value=[link])

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import get_protocol_link_from_eis

            result = await get_protocol_link_from_eis(page, "https://eis/tender")

        assert result == "https://other.site/protocol/123"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_protocol_links(self) -> None:
        """Returns None when no protocol links found."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import get_protocol_link_from_eis

            result = await get_protocol_link_from_eis(page, "https://eis/tender")

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_link_without_protocol_in_href(self) -> None:
        """Links whose href doesn't contain 'protocol' are skipped."""
        page = AsyncMock()

        link = AsyncMock()
        link.get_attribute = AsyncMock(return_value="/some/other/page")

        page.query_selector_all = AsyncMock(return_value=[link])

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import get_protocol_link_from_eis

            result = await get_protocol_link_from_eis(page, "https://eis/tender")

        assert result is None

    @pytest.mark.asyncio
    async def test_skips_link_with_none_href(self) -> None:
        """Links with href=None are skipped."""
        page = AsyncMock()

        link = AsyncMock()
        link.get_attribute = AsyncMock(return_value=None)

        page.query_selector_all = AsyncMock(return_value=[link])

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import get_protocol_link_from_eis

            result = await get_protocol_link_from_eis(page, "https://eis/tender")

        assert result is None


# ── Tests for download_protocol_from_eis ─────────────────────────────────────


class TestDownloadProtocolFromEis:
    """Tests for download_protocol_from_eis()."""

    @pytest.mark.asyncio
    async def test_successful_download(self, tmp_path: Path) -> None:
        """Downloads file and returns path."""
        mock_download = MagicMock()
        mock_download.suggested_filename = "protocol.docx"
        mock_download.save_as = AsyncMock()

        # Playwright's expect_download is an async CM where __aenter__
        # returns self and .value is an awaitable resolving to Download.
        async def _get_download():
            return mock_download

        class FakeEventInfo:
            def __init__(self):
                self.value = _get_download()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        page = AsyncMock()
        page.expect_download = MagicMock(return_value=FakeEventInfo())

        expected_dir = tmp_path / "1234567890" / "tender1" / "eis"

        with patch("src.scraper.eis_fallback.DOWNLOADS_DIR", tmp_path):
            from src.scraper.eis_fallback import download_protocol_from_eis

            # Create the file so stat() works
            expected_dir.mkdir(parents=True, exist_ok=True)
            (expected_dir / "protocol.docx").write_text("test")

            result = await download_protocol_from_eis(
                page, "https://eis/protocol", "tender1", "1234567890"
            )

        assert result is not None
        assert result.name == "protocol.docx"

    @pytest.mark.asyncio
    async def test_download_exception_returns_none(self, tmp_path: Path) -> None:
        """Returns None when download raises an exception."""
        page = AsyncMock()
        page.expect_download = MagicMock(side_effect=Exception("download error"))

        with patch("src.scraper.eis_fallback.DOWNLOADS_DIR", tmp_path):
            from src.scraper.eis_fallback import download_protocol_from_eis

            result = await download_protocol_from_eis(
                page, "https://eis/protocol", "tender1", "1234567890"
            )

        assert result is None


# ── Tests for fallback_extract_inn ───────────────────────────────────────────


class TestFallbackExtractInn:
    """Tests for fallback_extract_inn() — extracts INN via EIS link on page."""

    @pytest.mark.asyncio
    async def test_finds_eis_link_and_extracts_inn(self) -> None:
        """Finds EIS link on rostender page and delegates to extract_inn_from_eis."""
        page = AsyncMock()

        eis_link_el = AsyncMock()
        eis_link_el.get_attribute = AsyncMock(
            return_value="https://zakupki.gov.ru/order/123"
        )

        page.query_selector = AsyncMock(return_value=eis_link_el)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
            patch(
                "src.scraper.eis_fallback.extract_inn_from_eis",
                new_callable=AsyncMock,
                return_value="1112223334",
            ) as mock_extract,
        ):
            from src.scraper.eis_fallback import fallback_extract_inn

            result = await fallback_extract_inn(page, "https://rostender.info/t/1")

        assert result == "1112223334"
        mock_extract.assert_called_once_with(page, "https://zakupki.gov.ru/order/123")

    @pytest.mark.asyncio
    async def test_no_eis_link_returns_none(self) -> None:
        """Returns None when no EIS link found on the page."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import fallback_extract_inn

            result = await fallback_extract_inn(page, "https://rostender.info/t/1")

        assert result is None

    @pytest.mark.asyncio
    async def test_eis_link_with_no_href_returns_none(self) -> None:
        """Returns None when EIS link element has no href attribute."""
        page = AsyncMock()

        eis_link_el = AsyncMock()
        eis_link_el.get_attribute = AsyncMock(return_value=None)

        page.query_selector = AsyncMock(return_value=eis_link_el)

        with (
            patch("src.scraper.eis_fallback.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.eis_fallback.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.eis_fallback import fallback_extract_inn

            result = await fallback_extract_inn(page, "https://rostender.info/t/1")

        assert result is None


# ── Tests for fallback_get_protocol ──────────────────────────────────────────


class TestFallbackGetProtocol:
    """Tests for fallback_get_protocol() — downloads protocol via EIS."""

    @pytest.mark.asyncio
    async def test_finds_and_downloads_protocol(self) -> None:
        """When protocol link is found, downloads and returns path."""
        page = AsyncMock()
        expected_path = Path("/downloads/inn/tid/eis/protocol.docx")

        with (
            patch(
                "src.scraper.eis_fallback.get_protocol_link_from_eis",
                new_callable=AsyncMock,
                return_value="https://eis/protocol/dl",
            ),
            patch(
                "src.scraper.eis_fallback.download_protocol_from_eis",
                new_callable=AsyncMock,
                return_value=expected_path,
            ) as mock_download,
        ):
            from src.scraper.eis_fallback import fallback_get_protocol

            result = await fallback_get_protocol(
                page, "https://eis/tender/1", "tid", "inn"
            )

        assert result is expected_path
        mock_download.assert_called_once_with(
            page, "https://eis/protocol/dl", "tid", "inn"
        )

    @pytest.mark.asyncio
    async def test_no_protocol_link_returns_none(self) -> None:
        """Returns None when get_protocol_link_from_eis returns None."""
        page = AsyncMock()

        with patch(
            "src.scraper.eis_fallback.get_protocol_link_from_eis",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from src.scraper.eis_fallback import fallback_get_protocol

            result = await fallback_get_protocol(
                page, "https://eis/tender/1", "tid", "inn"
            )

        assert result is None
