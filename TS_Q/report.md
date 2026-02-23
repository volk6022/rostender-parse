# Code Review Report: Rostender Parser (Steps 1-6)

**Date:** 23.02.2026  
**Reviewer:** opencode  
**Scope:** Steps 1-6 implementation

---

## Executive Summary

Steps 1-6 are **mostly complete** (≈85%). Critical bugs exist that must be fixed before running. Steps 7-8 are not implemented.

---

## ✅ Completed Steps

| Step | Module | Files | Status |
|------|--------|-------|--------|
| 1 | Infrastructure | config.py, db/schema.py, db/repository.py | ✅ Done |
| 2 | Active Tenders | scraper/browser.py, scraper/active_tenders.py | ✅ Done |
| 3 | Historical Search | scraper/historical_search.py | ✅ Done |
| 4 | Protocol Parsing | parser/*.py (4 files) | ✅ Done |
| 5 | EIS Fallback | scraper/eis_fallback.py | ✅ Done |
| 6 | Competition Analyzer | analyzer/competition.py | ✅ Done |

---

## ❌ Not Implemented

| Step | Description | Status |
|------|-------------|--------|
| 7 | Extended Search (Stage 3) | ❌ Not implemented |
| 8 | Reports (Console + Excel) | ❌ Not implemented (empty reporter/) |

---

## 🐛 Critical Bugs (Must Fix)

### Bug 1: Incorrect Results Insertion Logic
**File:** `src/main.py:218-230`

**Problem:** Inserts results for ALL active tenders of customer, not just those from current search.

```python
# Current (wrong):
for active_tender in active_tenders_for_inn:
    await insert_result(...)  # Inserts for ALL tenders in DB
```

**Impact:** False positives in results.

---

### Bug 2: Missing eis_url for Historical Tenders
**File:** `src/main.py:163-172`

**Problem:** Historical tenders saved without `eis_url`, breaking fallback functionality.

```python
# Missing: eis_url=t_data.get("eis_url")
```

**Impact:** EIS fallback cannot work for historical tenders.

---

### Bug 3: parse_source Schema Mismatch
**File:** `src/parser/html_protocol.py:279`

**Problem:** Returns `"doc"` but schema expects `"doc_text"`.

```python
return (..., "doc")  # Should be "doc_text"
```

**Impact:** Database constraint violation possible.

---

### Bug 4: EIS Fallback Never Called
**File:** `src/main.py:183-201`

**Problem:** When rostender.info protocol parsing fails, never tries zakupki.gov.ru.

```python
result = await analyze_tender_protocol(...)  # Only primary source
# Missing: fallback to eis_fallback.py
```

**Impact:** Lower success rate for protocol analysis.

---

## ⚠️ Potential Issues

### Issue 1: Nested Database Connections
**File:** `src/main.py:135-142`

Connection opened twice unnecessarily. Works but inefficient.

---

### Issue 2: No Transaction Rollback
If error occurs mid-analysis, partial data remains in DB.

---

### Issue 3: No Retry Logic
Failed downloads don't retry.

---

### Issue 4: Missing publish_date Extraction
Historical tenders don't extract `publish_date` from search results.

---

### Issue 5: get_customer_name Limited Regex
**File:** `src/scraper/active_tenders.py:253`

May miss some organization types not in regex pattern.

---

## 📋 Required Fixes

### Priority 1 (Critical - Before Running)

1. **Fix results insertion logic** — main.py:218-230
2. **Add eis_url to historical tenders** — main.py:163-172
3. **Fix parse_source inconsistency** — html_protocol.py:279

### Priority 2 (Missing Features)

4. **Integrate EIS fallback** in historical analysis — main.py:183-201
5. **Implement reporter modules** — console_report.py, excel_report.py
6. **Implement extended search** — main.py:252-254 (Stage 7)

### Priority 3 (Quality Improvements)

7. Add transaction handling/rollback
8. Add retry logic for downloads

---

## 📁 Files Summary

| File | Lines | Status |
|------|-------|--------|
| config.py | 88 | ✅ Ready |
| db/schema.py | 56 | ✅ Ready |
| db/repository.py | 264 | ✅ Ready |
| scraper/browser.py | 86 | ✅ Ready |
| scraper/active_tenders.py | 268 | ⚠️ Minor issues |
| scraper/historical_search.py | 158 | ✅ Ready |
| scraper/eis_fallback.py | 284 | ✅ Ready |
| parser/html_protocol.py | 464 | ⚠️ Bug #3 |
| parser/docx_parser.py | 146 | ✅ Ready |
| parser/pdf_parser.py | 119 | ✅ Ready |
| parser/participant_patterns.py | 204 | ✅ Ready |
| analyzer/competition.py | 93 | ✅ Ready |
| main.py | 269 | ⚠️ Bugs #1, #2, #4 |
| reporter/*.py | — | ❌ Not implemented |

---

## ✅ Plan Compliance

| Plan Requirement | Implementation | Match |
|------------------|----------------|-------|
| SEARCH_KEYWORDS | config.py:13 | ✅ |
| EXCLUDE_KEYWORDS | config.py:26 | ✅ |
| MIN_PRICE_ACTIVE = 25M | config.py:47 | ✅ |
| MIN_PRICE_HISTORICAL = 1M | config.py:49 | ✅ |
| HISTORICAL_TENDERS_LIMIT = 5 | config.py:52 | ✅ |
| MAX_PARTICIPANTS_THRESHOLD = 2 | config.py:53 | ✅ |
| COMPETITION_RATIO_THRESHOLD = 0.8 | config.py:54 | ✅ |
| SQLite schema | db/schema.py | ✅ |
| Parsing chain (5 steps) | parser/html_protocol.py | ✅ |
| Competition calculation | analyzer/competition.py | ✅ |

---

## Next Steps

1. Fix Priority 1 bugs in main.py and html_protocol.py
2. Create reporter/ modules
3. Integrate EIS fallback
4. Implement extended search (optional for MVP)
5. Test end-to-end
