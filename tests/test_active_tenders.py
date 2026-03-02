"""Tests for src.scraper.active_tenders — active tender search and parsing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_tender_row(
    tid: str = "12345",
    title: str = "Поставка оборудования",
    href: str = "/region/tender/12345-tender",
    price_text: str = "5 000 000 ₽",
    *,
    has_link: bool = True,
    has_price: bool = True,
) -> AsyncMock:
    """Create a mock tender card (article.tender-row)."""
    row = AsyncMock()
    row.get_attribute = AsyncMock(return_value=tid)

    link_el = AsyncMock()
    link_el.inner_text = AsyncMock(return_value=f"  {title}  ")
    link_el.get_attribute = AsyncMock(return_value=href)

    price_el = AsyncMock()
    price_el.inner_text = AsyncMock(return_value=price_text)

    async def row_qs(sel: str):
        if "tender-info__description" in sel:
            return link_el if has_link else None
        if "tender-info__link" in sel:
            return link_el if has_link else None
        if "starting-price__price" in sel:
            return price_el if has_price else None
        return None

    row.query_selector = AsyncMock(side_effect=row_qs)
    return row


def _make_raw_tender_item(
    tid: str = "12345",
    title: str = "Поставка оборудования",
    url: str = "/region/tender/12345-tender",
    price_text: str = "5 000 000 ₽",
) -> dict:
    """Create a dict matching the shape returned by page.evaluate in parse_tenders_on_page.

    After Fix 1 the function extracts all card data in a single JS call;
    the return value from ``page.evaluate()`` is a list of these dicts.
    """
    return {
        "tender_id": tid or None,
        "title": title or None,
        "url": url,
        "price_text": price_text,
    }


# ── Tests for parse_tenders_on_page ──────────────────────────────────────────


class TestParseTendersOnPage:
    """Tests for parse_tenders_on_page().

    After Fix 1 the function uses a single ``page.evaluate()`` call instead
    of multiple ElementHandle round-trips, so tests now mock ``page.evaluate``
    rather than ``page.query_selector_all`` + per-row handles.
    """

    @pytest.mark.asyncio
    async def test_parses_single_tender(self) -> None:
        """Parses a single tender card correctly."""
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[_make_raw_tender_item()])

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert len(result) == 1
        assert result[0]["tender_id"] == "12345"
        assert result[0]["title"] == "Поставка оборудования"
        assert result[0]["price"] == 5000000.0
        assert result[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_relative_url_prefixed_with_base_url(self) -> None:
        """Relative URLs are prefixed with BASE_URL."""
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[_make_raw_tender_item(url="/region/tender/99")]
        )

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert result[0]["url"].startswith("https://rostender.info")

    @pytest.mark.asyncio
    async def test_absolute_url_not_prefixed(self) -> None:
        """Absolute URLs are not prefixed."""
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[_make_raw_tender_item(url="https://other.site/tender/99")]
        )

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert result[0]["url"] == "https://other.site/tender/99"

    @pytest.mark.asyncio
    async def test_no_rows_returns_empty(self) -> None:
        """When page.evaluate returns empty list, returns empty list."""
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[])

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert result == []

    @pytest.mark.asyncio
    async def test_skips_item_without_id(self) -> None:
        """Items without a tender_id are skipped during post-processing."""
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[
                {"tender_id": None, "title": "Test", "url": "/t", "price_text": "0"},
            ]
        )

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert result == []

    @pytest.mark.asyncio
    async def test_skips_item_without_title(self) -> None:
        """Items without a title (no link element in DOM) are skipped."""
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[
                {"tender_id": "99999", "title": None, "url": "/t", "price_text": "0"},
            ]
        )

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert result == []

    @pytest.mark.asyncio
    async def test_no_price_defaults_to_zero(self) -> None:
        """When price_text is '0', price defaults to 0."""
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[_make_raw_tender_item(price_text="0")])

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert result[0]["price"] == 0.0

    @pytest.mark.asyncio
    async def test_custom_tender_status(self) -> None:
        """tender_status parameter is used in the result."""
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[_make_raw_tender_item()])

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page, tender_status="completed")

        assert result[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_multiple_tenders(self) -> None:
        """Multiple tender cards are all parsed."""
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[
                _make_raw_tender_item(tid="1", title="First"),
                _make_raw_tender_item(tid="2", title="Second"),
                _make_raw_tender_item(tid="3", title="Third"),
            ]
        )

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert len(result) == 3
        assert [t["tender_id"] for t in result] == ["1", "2", "3"]

    @pytest.mark.asyncio
    async def test_exception_in_one_item_continues(self) -> None:
        """Exception post-processing one item doesn't stop processing others."""
        page = AsyncMock()
        # First item has price_text as a list → .replace() raises AttributeError
        page.evaluate = AsyncMock(
            return_value=[
                {"tender_id": "1", "title": "Bad", "url": "/t/1", "price_text": [1, 2]},
                _make_raw_tender_item(tid="2", title="Good"),
            ]
        )

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert len(result) == 1
        assert result[0]["tender_id"] == "2"

    @pytest.mark.asyncio
    async def test_evaluate_exception_returns_empty(self) -> None:
        """If page.evaluate raises (e.g. forceReload), returns empty list."""
        page = AsyncMock()
        page.evaluate = AsyncMock(
            side_effect=Exception("Execution context was destroyed")
        )

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert result == []

    @pytest.mark.asyncio
    async def test_price_with_comma_decimal(self) -> None:
        """Price with comma as decimal separator is parsed correctly."""
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[_make_raw_tender_item(price_text="1 234 567,89 ₽")]
        )

        from src.scraper.active_tenders import parse_tenders_on_page

        result = await parse_tenders_on_page(page)

        assert result[0]["price"] == 1234567.89


# ── Tests for extract_inn_from_page ──────────────────────────────────────────


class TestExtractInnFromPage:
    """Tests for extract_inn_from_page()."""

    @pytest.mark.asyncio
    async def test_finds_inn_in_button_attribute(self) -> None:
        """Finds INN from the inn attribute of the toggle button."""
        page = AsyncMock()

        btn = AsyncMock()
        btn.get_attribute = AsyncMock(return_value="  1234567890  ")

        page.query_selector = AsyncMock(return_value=btn)

        with (
            patch("src.scraper.active_tenders.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.active_tenders import extract_inn_from_page

            result = await extract_inn_from_page(page, "https://rostender/t/1")

        assert result == "1234567890"

    @pytest.mark.asyncio
    async def test_finds_inn_in_page_content_regex(self) -> None:
        """Falls back to regex search in page content."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.content = AsyncMock(return_value="<div>ИНН: 9876543210</div>")

        with (
            patch("src.scraper.active_tenders.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.active_tenders import extract_inn_from_page

            result = await extract_inn_from_page(page, "https://rostender/t/1")

        assert result == "9876543210"

    @pytest.mark.asyncio
    async def test_returns_none_when_inn_not_found(self) -> None:
        """Returns None when INN is not found anywhere."""
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.content = AsyncMock(return_value="<div>No INN here</div>")

        with (
            patch("src.scraper.active_tenders.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.active_tenders import extract_inn_from_page

            result = await extract_inn_from_page(page, "https://rostender/t/1")

        assert result is None

    @pytest.mark.asyncio
    async def test_button_with_empty_inn_falls_through(self) -> None:
        """Button with empty inn attribute falls through to content search."""
        page = AsyncMock()

        btn = AsyncMock()
        btn.get_attribute = AsyncMock(return_value="   ")

        # First call for inn_button returns btn, second for eis_link returns None
        async def mock_qs(sel: str):
            if "toggle-counterparty" in sel:
                return btn
            return None

        page.query_selector = AsyncMock(side_effect=mock_qs)
        page.content = AsyncMock(return_value="<span>ИНН 1111111111</span>")

        with (
            patch("src.scraper.active_tenders.safe_goto", new_callable=AsyncMock),
            patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.active_tenders import extract_inn_from_page

            result = await extract_inn_from_page(page, "https://rostender/t/1")

        assert result == "1111111111"


# ── Tests for get_customer_name ──────────────────────────────────────────────


class TestGetCustomerName:
    """Tests for get_customer_name()."""

    @pytest.mark.asyncio
    async def test_finds_org_name_in_quotes(self) -> None:
        """Finds organization name like ООО \"Name\" in page content."""
        page = AsyncMock()
        page.content = AsyncMock(
            return_value='<div>Заказчик: ООО "Ромашка и партнёры"</div>'
        )

        from src.scraper.active_tenders import get_customer_name

        result = await get_customer_name(page)

        assert result is not None
        assert "Ромашка" in result

    @pytest.mark.asyncio
    async def test_finds_name_via_organizer_block(self) -> None:
        """Finds name from Организатор/Заказчик block in HTML."""
        page = AsyncMock()
        # Regex: (?:Организатор|Заказчик)[^<]*?<[^>]*>([^<]{5,100})</[^>]*>
        # Needs: keyword + optional non-tag text + one tag + captured text + closing tag
        page.content = AsyncMock(
            return_value="<div>Организатор: <span>Администрация города Тестов</span></div>"
        )

        from src.scraper.active_tenders import get_customer_name

        result = await get_customer_name(page)

        assert result is not None
        assert "Администрация" in result

    @pytest.mark.asyncio
    async def test_returns_none_when_no_name_found(self) -> None:
        """Returns None when no organization name pattern matches."""
        page = AsyncMock()
        page.content = AsyncMock(
            return_value="<div>Some content without org names</div>"
        )

        from src.scraper.active_tenders import get_customer_name

        result = await get_customer_name(page)

        assert result is None


# ── Tests for _navigate_to_search ────────────────────────────────────────────


class TestNavigateToSearch:
    """Tests for _navigate_to_search() internal helper."""

    @pytest.mark.asyncio
    async def test_navigates_to_base_then_extsearch(self) -> None:
        """Navigates to BASE_URL first, then to extended search page."""
        page = AsyncMock()

        with (
            patch(
                "src.scraper.active_tenders.safe_goto", new_callable=AsyncMock
            ) as mock_goto,
            patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.active_tenders import _navigate_to_search

            await _navigate_to_search(page)

        assert mock_goto.call_count == 2
        first_url = mock_goto.call_args_list[0].args[1]
        second_url = mock_goto.call_args_list[1].args[1]
        assert first_url == "https://rostender.info"
        assert "extsearch/advanced" in second_url


# ── Tests for search_active_tenders ──────────────────────────────────────────


class TestSearchActiveTenders:
    """Tests for search_active_tenders() orchestration."""

    @pytest.mark.asyncio
    async def test_calls_navigate_and_fill_and_submit(self) -> None:
        """Verifies the full search flow: navigate → fill → submit."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch(
                "src.scraper.active_tenders._navigate_to_search",
                new_callable=AsyncMock,
            ) as mock_nav,
            patch(
                "src.scraper.active_tenders._fill_common_filters",
                new_callable=AsyncMock,
            ) as mock_fill,
            patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.active_tenders import search_active_tenders

            result = await search_active_tenders(
                page, keywords=["Test"], min_price=1000
            )

        mock_nav.assert_called_once()
        mock_fill.assert_called_once()
        fill_args = mock_fill.call_args.args
        assert fill_args[1] == ["Test"]
        assert fill_args[2] == 1000
        assert result == []

    @pytest.mark.asyncio
    async def test_fills_date_fields(self) -> None:
        """Date fields are filled with provided or default values."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch(
                "src.scraper.active_tenders._navigate_to_search",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.active_tenders._fill_common_filters",
                new_callable=AsyncMock,
            ),
            patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.active_tenders import search_active_tenders

            await search_active_tenders(
                page,
                keywords=["X"],
                date_from="01.01.2025",
                date_to="31.01.2025",
            )

        # page.fill called for date_from and date_to
        fill_calls = [(c.args[0], c.args[1]) for c in page.fill.call_args_list]
        date_from_calls = [c for c in fill_calls if "date-from" in c[0]]
        date_to_calls = [c for c in fill_calls if "date-to" in c[0]]
        assert len(date_from_calls) == 1
        assert date_from_calls[0][1] == "01.01.2025"
        assert len(date_to_calls) == 1
        assert date_to_calls[0][1] == "31.01.2025"


# ── Tests for search_tenders_by_inn ──────────────────────────────────────────


class TestSearchTendersByInn:
    """Tests for search_tenders_by_inn()."""

    @pytest.mark.asyncio
    async def test_fills_inn_field(self) -> None:
        """INN is filled in the customers input field."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)

        with (
            patch(
                "src.scraper.active_tenders._navigate_to_search",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.active_tenders._fill_common_filters",
                new_callable=AsyncMock,
            ),
            patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock),
        ):
            from src.scraper.active_tenders import search_tenders_by_inn

            await search_tenders_by_inn(page, "9998887776")

        # Should have filled the customers input with the INN
        fill_calls = [(c.args[0], c.args[1]) for c in page.fill.call_args_list]
        inn_calls = [c for c in fill_calls if c[1] == "9998887776"]
        assert len(inn_calls) == 1


# ── Tests for _fill_common_filters ────────────────────────────────────────────


class TestFillCommonFilters:
    """Tests for _fill_common_filters() internal helper."""

    @pytest.mark.asyncio
    async def test_fills_keywords_input(self) -> None:
        """Fills the keywords input with comma-joined keywords."""
        page = AsyncMock()

        with patch(
            "src.scraper.active_tenders.EXCLUDE_KEYWORDS", ["Аренда", "Строительство"]
        ):
            from src.scraper.active_tenders import _fill_common_filters

            await _fill_common_filters(page, ["ИТ", "Серверы"], min_price=5_000_000)

        # First page.fill call should be keywords
        fill_calls = page.fill.call_args_list
        assert fill_calls[0].args == ("#keywords", "ИТ, Серверы")

    @pytest.mark.asyncio
    async def test_fills_exceptions_input(self) -> None:
        """Fills the exceptions input with EXCLUDE_KEYWORDS."""
        page = AsyncMock()

        with patch(
            "src.scraper.active_tenders.EXCLUDE_KEYWORDS", ["Аренда", "Строительство"]
        ):
            from src.scraper.active_tenders import _fill_common_filters

            await _fill_common_filters(page, ["ИТ"], min_price=1_000_000)

        fill_calls = page.fill.call_args_list
        assert fill_calls[1].args == ("#exceptions", "Аренда, Строительство")

    @pytest.mark.asyncio
    async def test_sets_min_price_via_evaluate(self) -> None:
        """Sets minimum price via page.evaluate (JS hidden field)."""
        page = AsyncMock()

        with patch("src.scraper.active_tenders.EXCLUDE_KEYWORDS", []):
            from src.scraper.active_tenders import _fill_common_filters

            await _fill_common_filters(page, ["X"], min_price=25_000_000)

        # page.evaluate is called multiple times; first one sets the price
        evaluate_calls = page.evaluate.call_args_list
        price_call = evaluate_calls[0]
        # Second arg is [str(min_price), selector_price, selector_disp]
        assert price_call.args[1] == ["25000000", "#min_price", "#min_price-disp"]

    @pytest.mark.asyncio
    async def test_sets_hide_price_checkbox(self) -> None:
        """Sets the hide-without-price checkbox via JS."""
        page = AsyncMock()

        with patch("src.scraper.active_tenders.EXCLUDE_KEYWORDS", []):
            from src.scraper.active_tenders import _fill_common_filters

            await _fill_common_filters(page, ["X"], min_price=1000)

        evaluate_calls = page.evaluate.call_args_list
        hide_price_call = evaluate_calls[1]
        assert hide_price_call.args[1] == "#hide_price"

    @pytest.mark.asyncio
    async def test_sets_states_to_accepting_bids(self) -> None:
        """Sets the states select to value '10' (Прием заявок)."""
        page = AsyncMock()

        with patch("src.scraper.active_tenders.EXCLUDE_KEYWORDS", []):
            from src.scraper.active_tenders import _fill_common_filters

            await _fill_common_filters(page, ["X"], min_price=1000)

        evaluate_calls = page.evaluate.call_args_list
        states_call = evaluate_calls[2]
        assert states_call.args[1] == ["10", "#states"]

    @pytest.mark.asyncio
    async def test_excludes_auction_and_single_supplier(self) -> None:
        """Excludes placement ways '1' (Аукцион) and '28' (Ед. поставщик)."""
        page = AsyncMock()

        with patch("src.scraper.active_tenders.EXCLUDE_KEYWORDS", []):
            from src.scraper.active_tenders import _fill_common_filters

            await _fill_common_filters(page, ["X"], min_price=1000)

        evaluate_calls = page.evaluate.call_args_list
        placement_call = evaluate_calls[3]
        assert placement_call.args[1] == [["1", "28"], "#placement_ways"]

    @pytest.mark.asyncio
    async def test_total_evaluate_calls(self) -> None:
        """Exactly 4 page.evaluate calls: price, checkbox, states, placement."""
        page = AsyncMock()

        with patch("src.scraper.active_tenders.EXCLUDE_KEYWORDS", []):
            from src.scraper.active_tenders import _fill_common_filters

            await _fill_common_filters(page, ["X"], min_price=1000)

        assert page.evaluate.call_count == 4


# ── Tests for _submit_and_collect ─────────────────────────────────────────────


class TestSubmitAndCollect:
    """Tests for _submit_and_collect() internal helper."""

    @pytest.mark.asyncio
    async def test_clicks_search_button(self) -> None:
        """Clicks the search button to submit the form."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)

        with patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock):
            from src.scraper.active_tenders import _submit_and_collect

            await _submit_and_collect(page)

        page.click.assert_called_once_with("#start-search-button")

    @pytest.mark.asyncio
    async def test_waits_for_load_state(self) -> None:
        """Waits for 'load' state after clicking search."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)

        with patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock):
            from src.scraper.active_tenders import _submit_and_collect

            await _submit_and_collect(page)

        page.wait_for_load_state.assert_called_with("load")

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self) -> None:
        """Returns empty list when no tender cards are found."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)

        with patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock):
            from src.scraper.active_tenders import _submit_and_collect

            result = await _submit_and_collect(page)

        assert result == []

    @pytest.mark.asyncio
    async def test_collects_tenders_from_single_page(self) -> None:
        """Collects tenders from a single results page (no pagination)."""
        page = AsyncMock()
        sentinel = MagicMock()  # non-empty list for rows-exist check

        # query_selector_all: rows-exist check returns non-empty
        page.query_selector_all = AsyncMock(return_value=[sentinel])
        # page.evaluate: parse_tenders_on_page returns parsed data
        page.evaluate = AsyncMock(
            return_value=[_make_raw_tender_item(tid="42", title="Tender 42")]
        )
        # No next button → stop pagination
        page.query_selector = AsyncMock(return_value=None)

        with patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock):
            from src.scraper.active_tenders import _submit_and_collect

            result = await _submit_and_collect(page)

        assert len(result) == 1
        assert result[0]["tender_id"] == "42"

    @pytest.mark.asyncio
    async def test_pagination_follows_next_button(self) -> None:
        """Follows pagination next button across multiple pages."""
        page = AsyncMock()
        sentinel = MagicMock()

        # _submit_and_collect calls query_selector_all once per page for rows check.
        # Page 1: [sentinel]; Page 2: [sentinel]; Page 3: [] (stop).
        qsa_count = 0

        async def mock_query_selector_all(sel: str):
            nonlocal qsa_count
            qsa_count += 1
            if qsa_count <= 2:
                return [sentinel]
            return []

        page.query_selector_all = AsyncMock(side_effect=mock_query_selector_all)

        # page.evaluate: parse_tenders_on_page extracts data.
        # Called once per page with rows.
        eval_count = 0

        async def mock_evaluate(js, args=None):
            nonlocal eval_count
            eval_count += 1
            if eval_count == 1:
                return [_make_raw_tender_item(tid="1", title="First")]
            return [_make_raw_tender_item(tid="2", title="Second")]

        page.evaluate = AsyncMock(side_effect=mock_evaluate)

        # Next button: present after page 1, absent after page 2
        next_btn = AsyncMock()
        qs_count = 0

        async def mock_query_selector(sel: str):
            nonlocal qs_count
            qs_count += 1
            if qs_count == 1:
                return next_btn
            return None

        page.query_selector = AsyncMock(side_effect=mock_query_selector)

        with patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock):
            from src.scraper.active_tenders import _submit_and_collect

            result = await _submit_and_collect(page)

        assert len(result) == 2
        assert next_btn.click.called

    @pytest.mark.asyncio
    async def test_stops_when_no_next_button(self) -> None:
        """Stops pagination when no next button is found."""
        page = AsyncMock()
        sentinel = MagicMock()
        page.query_selector_all = AsyncMock(return_value=[sentinel])
        page.evaluate = AsyncMock(return_value=[_make_raw_tender_item()])
        page.query_selector = AsyncMock(return_value=None)

        with patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock):
            from src.scraper.active_tenders import _submit_and_collect

            result = await _submit_and_collect(page)

        # Should only parse one page
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_polite_wait_called_after_submit_and_pagination(self) -> None:
        """polite_wait is called after search submit and after each pagination."""
        page = AsyncMock()
        sentinel = MagicMock()

        # Page 1: rows exist, Page 2: no rows (empty)
        call_idx = 0

        async def mock_qsa(sel: str):
            nonlocal call_idx
            call_idx += 1
            return [sentinel] if call_idx == 1 else []

        page.query_selector_all = AsyncMock(side_effect=mock_qsa)
        page.evaluate = AsyncMock(return_value=[_make_raw_tender_item()])

        next_btn = AsyncMock()
        qs_idx = 0

        async def mock_qs(sel: str):
            nonlocal qs_idx
            qs_idx += 1
            return next_btn if qs_idx == 1 else None

        page.query_selector = AsyncMock(side_effect=mock_qs)

        with patch(
            "src.scraper.active_tenders.polite_wait", new_callable=AsyncMock
        ) as mock_wait:
            from src.scraper.active_tenders import _submit_and_collect

            await _submit_and_collect(page)

        # polite_wait called: once after submit, once after clicking next
        assert mock_wait.call_count == 2

    @pytest.mark.asyncio
    async def test_log_context_passed_through(self) -> None:
        """log_context parameter is used (no crash with custom context)."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=None)

        with patch("src.scraper.active_tenders.polite_wait", new_callable=AsyncMock):
            from src.scraper.active_tenders import _submit_and_collect

            # Should not raise
            result = await _submit_and_collect(
                page,
                log_context="для ИНН 1234567890",
                empty_warning="Тендеры не найдены",
            )
