"""Тесты для src/scraper/historical_search.py — extract_keywords + search_historical_tenders."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scraper.historical_search import extract_keywords_from_title


class TestExtractKeywordsFromTitle:
    """Тесты для extract_keywords_from_title()."""

    def test_full_title_not_first_keyword(self):
        """Full raw title is NOT added as a keyword (Fix 3)."""
        result = extract_keywords_from_title("Поставка оборудования")
        # The first keyword should be the first meaningful phrase, not the raw title
        # (for short titles they may coincide, but the logic is different)
        assert len(result) >= 1
        # All keywords must be <= 60 chars (no raw 100+ char titles)
        for kw in result:
            assert len(kw) <= 60

    def test_leading_number_stripped(self):
        """Leading tender numbers/codes are stripped from keywords."""
        result = extract_keywords_from_title(
            "223785 Ремонт тепловой изоляции на 2026-2028 гг."
        )
        # "223785" should not appear in any keyword
        for kw in result:
            assert "223785" not in kw

    def test_short_words_excluded(self):
        """Слова короче 4 символов не включаются через regex \\b\\w{4,}."""
        result = extract_keywords_from_title("На и от для тестирование")
        lower_results = [r.lower() for r in result]
        assert "на" not in lower_results
        assert "от" not in lower_results

    def test_stopwords_excluded(self):
        """Стоп-слова (для, что, это, ...) не включаются как important_words."""
        result = extract_keywords_from_title("Товар для этого котор таким")
        lower_results = [r.lower() for r in result]
        for sw in ["для", "котор", "таким"]:
            assert sw not in lower_results

    def test_first_part_before_comma(self):
        """Первая часть до запятой добавляется как ключевое слово."""
        result = extract_keywords_from_title(
            "Поставка электрооборудования, включая монтаж"
        )
        assert "Поставка электрооборудования" in result

    def test_first_part_before_bracket(self):
        """Первая часть до скобки добавляется."""
        result = extract_keywords_from_title(
            "Капитальный ремонт (включая проектирование)"
        )
        assert "Капитальный ремонт" in result

    def test_long_first_part_capped_at_60(self):
        """First phrase longer than 60 chars is truncated at word boundary."""
        long_phrase = "Поставка электротехнического оборудования и специализированных комплектующих материалов"
        result = extract_keywords_from_title(long_phrase)
        # First keyword (the phrase) should be <= 60 chars
        if result:
            assert len(result[0]) <= 60

    def test_max_10_keywords(self):
        """Результат ограничен 10 ключевыми словами."""
        long_title = " ".join(f"Слово{i}Длинное" for i in range(20))
        result = extract_keywords_from_title(long_title)
        assert len(result) <= 10

    def test_deduplication(self):
        """Дубликаты (по lower) удаляются."""
        result = extract_keywords_from_title("Поставка поставка ПОСТАВКА")
        lower_results = [r.lower() for r in result]
        count = lower_results.count("поставка")
        assert count <= 1

    def test_empty_title(self):
        """Пустой заголовок — возвращается пустой список."""
        result = extract_keywords_from_title("")
        assert result == []

    def test_whitespace_only_title(self):
        """Whitespace-only title returns empty list."""
        result = extract_keywords_from_title("   ")
        assert result == []

    def test_short_title_included_as_word(self):
        """Короткий заголовок (<= 10 chars) — first_part not extracted, but word may be."""
        result = extract_keywords_from_title("Ремонт")
        # "Ремонт" is 6 chars > 5, should appear as capitalized important word
        assert any("ремонт" in r.lower() for r in result)

    @patch("src.config.SEARCH_KEYWORDS", ["Поставка", "Ремонт"])
    def test_search_keywords_matched_in_title(self):
        """SEARCH_KEYWORDS, совпадающие с заголовком, включаются."""
        result = extract_keywords_from_title(
            "Поставка строительных материалов для ремонтных работ"
        )
        assert "Поставка" in result

    @patch("src.config.SEARCH_KEYWORDS", ["Оборудование"])
    def test_search_keywords_not_matched(self):
        """SEARCH_KEYWORDS, не совпадающие с заголовком, не включаются."""
        result = extract_keywords_from_title("Уборка территории")
        assert "Оборудование" not in result

    def test_important_words_capitalized(self):
        """Важные слова (>5 символов) добавляются с заглавной буквой."""
        result = extract_keywords_from_title("поставка строительного оборудования")
        # Should have capitalized versions of long words
        has_capitalized = any(r[0].isupper() for r in result if len(r) > 5)
        assert has_capitalized

    def test_words_shorter_than_4_not_added_individually(self):
        """Слова < 4 символов не добавляются как отдельные ключевые слова."""
        result = extract_keywords_from_title("Тест крыша пол")
        # Filter out the first_part phrase to check individual words
        lower_results = [r.lower() for r in result if len(r.split()) == 1]
        assert "пол" not in lower_results  # 3 chars, not >= 4
        assert "крыша" in lower_results  # 5 chars, is >= 4


# ── Tests for search_historical_tenders ──────────────────────────────────────


class TestSearchHistoricalTenders:
    """Tests for the search_historical_tenders() async function."""

    @pytest.mark.asyncio
    async def test_no_results_found(self) -> None:
        """Returns empty list when no tender cards found on first page."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.url = "https://rostender.info/extsearch/result"

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            result = await search_historical_tenders(page, "1234567890", limit=5)

        assert result == []

    @pytest.mark.asyncio
    async def test_fills_inn_and_keywords(self) -> None:
        """Fills INN in customer field and keywords in search field."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.url = "https://rostender.info/extsearch/result"

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            await search_historical_tenders(
                page,
                "9876543210",
                custom_keywords=["Поставка", "Оборудование"],
            )

        fill_calls = [(c.args[0], c.args[1]) for c in page.fill.call_args_list]
        # Should have filled customers input with INN
        inn_calls = [c for c in fill_calls if c[1] == "9876543210"]
        assert len(inn_calls) == 1
        # Should have filled keywords input with joined keywords
        kw_calls = [c for c in fill_calls if "Поставка" in c[1]]
        assert len(kw_calls) == 1

    @pytest.mark.asyncio
    async def test_uses_custom_keywords_when_provided(self) -> None:
        """Custom keywords override SEARCH_KEYWORDS."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.url = "https://rostender.info/extsearch/result"

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            await search_historical_tenders(
                page, "1111111111", custom_keywords=["CustomKW"]
            )

        fill_calls = [(c.args[0], c.args[1]) for c in page.fill.call_args_list]
        kw_calls = [c for c in fill_calls if "CustomKW" in c[1]]
        assert len(kw_calls) == 1

    @pytest.mark.asyncio
    async def test_collects_tenders_from_page(self) -> None:
        """Collects parsed tenders from parse_tenders_on_page."""
        page = AsyncMock()
        # First call: rows exist; second call (next page check): no rows
        page.query_selector_all = AsyncMock(
            side_effect=[
                [MagicMock()],  # rows on page 1
                [],  # no rows on page 2
            ]
        )
        page.query_selector = AsyncMock(return_value=None)  # no next button
        page.url = "https://rostender.info/extsearch/result"

        parsed_tenders = [
            {
                "tender_id": "t1",
                "title": "T1",
                "url": "/t1",
                "price": 1000,
                "status": "completed",
            },
            {
                "tender_id": "t2",
                "title": "T2",
                "url": "/t2",
                "price": 2000,
                "status": "completed",
            },
        ]

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.parse_tenders_on_page",
                new_callable=AsyncMock,
                return_value=parsed_tenders,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            result = await search_historical_tenders(page, "1234567890", limit=10)

        assert len(result) == 2
        assert result[0]["tender_id"] == "t1"
        assert result[1]["tender_id"] == "t2"

    @pytest.mark.asyncio
    async def test_respects_limit(self) -> None:
        """Result is truncated to limit even if more tenders found."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        page.query_selector = AsyncMock(return_value=None)
        page.url = "https://rostender.info/extsearch/result"

        many_tenders = [
            {
                "tender_id": f"t{i}",
                "title": f"T{i}",
                "url": f"/t{i}",
                "price": 1000,
                "status": "completed",
            }
            for i in range(10)
        ]

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.parse_tenders_on_page",
                new_callable=AsyncMock,
                return_value=many_tenders,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            result = await search_historical_tenders(page, "1234567890", limit=3)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_pagination_follows_next_button(self) -> None:
        """Follows pagination when next button exists and limit not reached."""
        page = AsyncMock()
        page.url = "https://rostender.info/extsearch/result"

        next_btn = AsyncMock()
        call_count = 0

        async def mock_query_selector_all(sel: str):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Pages 1 and 2 have rows
                return [MagicMock()]
            return []  # Page 3 has no rows

        page.query_selector_all = AsyncMock(side_effect=mock_query_selector_all)

        # Next button exists on page 1, not on page 2
        qs_call = 0

        async def mock_query_selector(sel: str):
            nonlocal qs_call
            qs_call += 1
            if qs_call == 1:
                return next_btn  # Page 1 has next
            return None  # Page 2 has no next

        page.query_selector = AsyncMock(side_effect=mock_query_selector)

        page1_tenders = [
            {
                "tender_id": "t1",
                "title": "T1",
                "url": "/t1",
                "price": 1000,
                "status": "completed",
            },
        ]
        page2_tenders = [
            {
                "tender_id": "t2",
                "title": "T2",
                "url": "/t2",
                "price": 2000,
                "status": "completed",
            },
        ]

        parse_calls = 0

        async def mock_parse(pg, *, tender_status="completed"):
            nonlocal parse_calls
            parse_calls += 1
            if parse_calls == 1:
                return page1_tenders
            return page2_tenders

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.parse_tenders_on_page",
                new_callable=AsyncMock,
                side_effect=mock_parse,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            result = await search_historical_tenders(page, "1234567890", limit=10)

        assert len(result) == 2
        next_btn.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_stops_pagination_when_limit_reached(self) -> None:
        """Stops paginating when limit is reached mid-page."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        page.query_selector = AsyncMock(return_value=AsyncMock())  # next button exists
        page.url = "https://rostender.info/extsearch/result"

        tenders = [
            {
                "tender_id": f"t{i}",
                "title": f"T{i}",
                "url": f"/t{i}",
                "price": 1000,
                "status": "completed",
            }
            for i in range(5)
        ]

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.parse_tenders_on_page",
                new_callable=AsyncMock,
                return_value=tenders,
            ) as mock_parse,
        ):
            from src.scraper.historical_search import search_historical_tenders

            result = await search_historical_tenders(page, "1234567890", limit=3)

        assert len(result) == 3
        # Should only parse one page since limit was exceeded
        assert mock_parse.call_count == 1

    @pytest.mark.asyncio
    async def test_navigates_to_extsearch(self) -> None:
        """Navigates to the extended search page."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.url = "https://rostender.info/extsearch/result"

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ) as mock_goto,
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            await search_historical_tenders(page, "1234567890")

        goto_url = mock_goto.call_args.args[1]
        assert "extsearch/advanced" in goto_url

    @pytest.mark.asyncio
    async def test_clicks_search_button(self) -> None:
        """Clicks the search button after filling filters."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.url = "https://rostender.info/extsearch/result"

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            await search_historical_tenders(page, "1234567890")

        # Should have clicked the search button
        click_calls = [c.args[0] for c in page.click.call_args_list]
        assert any("start-search" in sel for sel in click_calls)

    @pytest.mark.asyncio
    async def test_waits_for_load_after_search(self) -> None:
        """Uses wait_for_load_state('load') after clicking search (Fix 2)."""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.url = "https://rostender.info/extsearch/result"

        with (
            patch(
                "src.scraper.historical_search.safe_goto",
                new_callable=AsyncMock,
            ),
            patch(
                "src.scraper.historical_search.polite_wait",
                new_callable=AsyncMock,
            ),
        ):
            from src.scraper.historical_search import search_historical_tenders

            await search_historical_tenders(page, "1234567890")

        # Should use "load" not "domcontentloaded"
        load_calls = [c.args[0] for c in page.wait_for_load_state.call_args_list]
        assert "load" in load_calls
