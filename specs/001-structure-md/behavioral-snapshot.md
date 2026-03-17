# Behavioral Snapshot: Scraper Fallbacks

**Refactor ID**: refactor-001
**Snapshot Date**: Tue Mar 17 2026

## Core Behaviors to Preserve

### 1. INN Extraction via Unified Fallback (EIS)
- **Input**: `source_urls_str` containing an EIS link.
- **Expected Behavior**: Correctly navigates to EIS and extracts the INN.
- **Test Command**: `pytest tests/test_eis_fallback.py`

### 2. Fallback Priority Order
- **Input**: `source_urls_str = "gpb:url,eis:url"`
- **Expected Behavior**: EIS is attempted before GPB.
- **Verification**: `unified_fallback.py` logic follows the list `["eis", "gpb", "rosatom", "roseltorg"]`.

### 3. Graceful Failure
- **Input**: Multiple source URLs, where the first one is invalid.
- **Expected Behavior**: Logs the failure and proceeds to the next source without crashing.
- **Verification**: Logs show "Ошибка фоллбэка [platform]" followed by "Пробуем фоллбэк [next_platform]".

## Verification Checklist
- [ ] `pytest tests/test_eis_fallback.py` - PASS
- [ ] `pytest tests/test_source_links.py` - PASS
- [ ] Manual test of `unified_fallback_extract_inn` with mixed valid/invalid URLs - PASS
