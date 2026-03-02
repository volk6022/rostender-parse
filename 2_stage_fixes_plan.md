# Stage 2 (analyze-history) — Plan of 4 Fixes

## Problem Summary

Stage 2 searches completed tenders by customer INN and parses their protocols to count
participants.  Currently it finds 0 valid protocols because of 3 critical bugs and 1 medium issue.

**Evidence from logs (`data/rostender.log`)**:
- Lines 2883-2961: INN `0277077282` — 20 cards found, all 20 fail with "Execution context was destroyed", 0 tenders returned.
- INN `7736050003` — 5 "completed" tenders found, but all are actually active (stage "Прием заявок"), so no protocol files exist.
- All 8 `protocol_analysis` records have `parse_status="no_protocol"`.

---

## Fix 1 (CRITICAL): `parse_tenders_on_page()` — Eliminate ElementHandle Staleness

**File:** `src/scraper/active_tenders.py` (lines 159-223)

### Root Cause

The site has a JS function `forceReload()` that calls `document.location.reload()` on first
visit per day (uses `localStorage` hash via `CryptoJS.MD5`).  Since Playwright uses a clean
browser context (no localStorage), **every results page reloads** right after initial load.

The current `parse_tenders_on_page()` uses multiple `ElementHandle` round-trips per card:
```python
for row in rows:                           # ElementHandle
    tender_id = await row.get_attribute("id")   # round-trip 1
    link_el = await row.query_selector(...)     # round-trip 2
    title = await link_el.inner_text()          # round-trip 3
    url = await link_el.get_attribute("href")   # round-trip 4
    price_el = await row.query_selector(...)    # round-trip 5
    price_text = await price_el.inner_text()    # round-trip 6
```

When `forceReload()` fires between any two of these calls, all ElementHandles become stale
-> "Execution context was destroyed" errors.

### Fix

Replace the entire for-loop with a **single `page.evaluate()`** that extracts all card data
atomically in one JS execution:

```python
async def parse_tenders_on_page(page, *, tender_status="active"):
    tenders_data = await page.evaluate("""
        (selectors) => {
            const rows = document.querySelectorAll(selectors.card);
            return Array.from(rows).map(row => {
                const id = row.getAttribute('id');
                const linkEl = row.querySelector(selectors.link)
                             || row.querySelector(selectors.linkAlt);
                const priceEl = row.querySelector(selectors.price);
                return {
                    tender_id: id || null,
                    title: linkEl ? linkEl.innerText.trim() : null,
                    url: linkEl ? linkEl.getAttribute('href') : null,
                    price_text: priceEl ? priceEl.innerText : '0',
                };
            }).filter(t => t.tender_id && t.title);
        }
    """, {...selectors...})
    # Post-process in Python: URL prefix, price parsing, add status
```

**Why it works:** `page.evaluate()` runs synchronously in the browser's JS context.  Even if
`forceReload()` triggers after it completes, all data is already extracted.  No stale handles.

**Callers affected:** None — function signature (`page, *, tender_status`) and return type
(`list[dict]`) are unchanged.

**Tests affected:** `tests/test_active_tenders.py` — `TestParseTendersOnPage` (~10 methods)
currently mock `page.query_selector_all` + `row.get_attribute`.  Will need to mock
`page.evaluate` instead.

---

## Fix 2 (CRITICAL): `search_historical_tenders()` — Proper Filter Application

**File:** `src/scraper/historical_search.py` (lines 89-257)

### Root Cause

Three sub-issues cause the "Завершён" (Completed) stage filter to not actually apply:

#### 2a. No wait after navigating to `/extsearch/advanced`

Line 144 calls `safe_goto()` then immediately starts filling form fields.  The page's jQuery
and Chosen plugin may not be initialized yet.

Compare: `active_tenders.py:25-29` does `safe_goto(BASE_URL)` -> `polite_wait()` ->
`safe_goto(extsearch/advanced)` (two-step navigation with wait).

**Fix:** Add `await polite_wait()` and wait for Chosen container (`#states_chosen`) after
navigation.

#### 2b. Chosen plugin update not verified

Lines 177-187 set `opt.selected` and trigger `chosen:updated`, but:
- No check that jQuery/Chosen is actually loaded
- No verification that the value was actually applied

**Fix:** Add `typeof jQuery !== 'undefined'` guard and return the selected value for
debug logging.

#### 2c. `wait_for_load_state("domcontentloaded")` too early

Line 193 uses `"domcontentloaded"` after clicking search.  This fires before all JS
(including `forceReload`) runs.  Compare: `_submit_and_collect()` in active_tenders.py:117
already uses `"load"`.

**Fix:** Change to `"load"` + add `await polite_wait()`.  Also fix line 245 (pagination).

### Tests affected

`tests/test_historical_search.py` — `TestSearchHistoricalTenders`.  Mock expectations for
`page.wait_for_load_state` and `page.evaluate` args need updating.

---

## Fix 3 (MEDIUM): `extract_keywords_from_title()` — Keywords Too Long

**File:** `src/scraper/historical_search.py` (lines 19-86)

### Root Cause

Line 40 (`keywords.append(title)`) adds the **full raw title** as the first keyword.
Example: `"223785 Ремонт тепловой изоляции и обмуровки оборудования на 2026-2028 гг.
для Уфимского узла ООО «БГК»..."` (160+ chars).

The search form treats this as a single search query where all words must match, severely
limiting results.

### Fix

1. **Remove** `keywords.append(title)` — never add the full raw title.
2. **Strip leading numbers/codes** from the title before extracting keywords
   (e.g., `"223785 Ремонт..." -> "Ремонт..."`).
3. **Cap** the `first_part` (before comma/parenthesis) at ~60 chars, cutting at word boundary.
4. Keep the rest of the keyword generation logic (individual words, SEARCH_KEYWORDS matching).

### Tests affected

`tests/test_historical_search.py` — `TestExtractKeywords` (~8 methods).  Tests that check
`title` is the first keyword will need updating.

---

## Fix 4 (MEDIUM): Diagnostic Logging

**Files:** `src/parser/html_protocol.py`, `src/scraper/historical_search.py`

No behavioral change — just better visibility for debugging.

### Changes

1. **`_find_protocol_files()`** (`html_protocol.py:99`):
   - Always log `files_by_date` count (even when no protocols found).
   - Log total file count across all dates.

2. **`analyze_tender_protocol()`** (`html_protocol.py:420`):
   - Log the tender's stage/status if visible on the page (helps catch "active tenders
     mistakenly treated as completed").

3. **`search_historical_tenders()`** (`historical_search.py`):
   - Log the actual selected `#states` value after setting it (covered by Fix 2b).
   - Log the current page URL after search to verify parameters were applied.

### Tests affected

None — logging-only changes.

---

## Execution Order

| Step | Fix | Files Modified | Tests to Update |
|------|-----|---------------|-----------------|
| 1 | Fix 1 (parse_tenders) | `src/scraper/active_tenders.py` | `tests/test_active_tenders.py` |
| 2 | Fix 3 (keywords) | `src/scraper/historical_search.py` | `tests/test_historical_search.py` |
| 3 | Fix 2 (filter/timing) | `src/scraper/historical_search.py` | `tests/test_historical_search.py` |
| 4 | Fix 4 (logging) | `src/parser/html_protocol.py`, `src/scraper/historical_search.py` | — |
| 5 | Run full test suite | — | — |

## Verification After All Fixes

```bash
# 1. Run tests
uv run pytest tests/ -v

# 2. Reset test customer in DB
# UPDATE customers SET status = 'new' WHERE inn = '0277077282';
# DELETE FROM protocol_analysis WHERE tender_id IN (SELECT tender_id FROM tenders WHERE customer_inn = '0277077282');

# 3. Run Stage 2 in visible mode
uv run python -m src.main analyze-history --no-headless
```

## Total Scope

- **3 source files** modified
- **2 test files** updated
- No new files, no signature changes, no DB schema changes
