# Stage 2 Fixes — Plan

Два блока изменений: баг-фикс фильтра «Этап» и фича `source_urls`.

---

## Блок 1: Баг-фикс фильтра «Этап» (high priority)

### Проблема

`search_historical_tenders` устанавливает `#states` = `"100"` (Завершён) через JS, но форма **игнорирует** это значение при сабмите. Результат — возвращаются тендеры со статусом «Приём заявок» вместо «Завершён».

### Причина

Chosen-плагин перехватывает native `<select>` и рисует свой UI. При программном изменении `<select>` нужно:
1. `trigger('chosen:updated')` — обновить визуал Chosen (**делается**)
2. `trigger('change')` — уведомить JS формы об изменении (**не делается**)

Без `change` форма не знает, что фильтр изменился, и при сабмите может отправить дефолтное значение.

### Фикс

#### 1. `src/scraper/historical_search.py:218-233`

Добавить `jQuery(select).trigger('change')` после `trigger('chosen:updated')`:

```javascript
// Было:
jQuery(select).trigger('chosen:updated');

// Станет:
jQuery(select).trigger('chosen:updated');
jQuery(select).trigger('change');
```

#### 2. `src/scraper/active_tenders.py:73-82` (states) и `85-100` (placement_ways)

Для консистентности — добавить `trigger('change')` в оба evaluate-блока `_fill_common_filters`:

```javascript
$(select).trigger('chosen:updated');
$(select).trigger('change');  // добавить
```

#### Затрагивает тесты

- `test_active_tenders.py` — `TestFillCommonFilters` проверяет содержимое JS-строк, но не вызовы jQuery, так что тесты не сломаются. Убедимся при прогоне.

---

## Блок 2: `source_urls` вместо `eis_url`

### Контекст

Колонка `eis_url` в таблице `tenders` существует, функция `upsert_tender` принимает параметр `eis_url`, но **ни один вызов `upsert_tender` никогда не передаёт `eis_url`** — она всегда NULL.

Ссылка на ЕИС доступна на странице каждого тендера на rostender.info как `<a href="...zakupki.gov.ru...">`, но нигде не извлекается и не сохраняется.

В будущем планируется фоллбэк не только на ЕИС, но и на другие сайты — поэтому вместо `eis_url` делаем универсальное поле `source_urls`.

### Архитектура

```
┌─────────────────────────┐
│ scraper/source_links.py │  ← новый модуль
│                         │
│ SOURCE_DOMAINS = {      │  ← маппинг домен → имя источника
│   "zakupki.gov.ru":"eis"│
│   "etpgpb.ru": "gpb",  │  ← будущие источники
│   ...                   │
│ }                       │
│                         │
│ extract_source_urls()   │  ← a[href] → фильтр по SOURCE_DOMAINS
│ get_source_url()        │  ← получить URL конкретного источника
│ parse_source_urls()     │  ← строку в dict
└─────────────────────────┘
```

### Формат хранения

Колонка `source_urls TEXT` в таблице `tenders`. Формат: через запятую, `source_name:url`.

Пример: `eis:https://zakupki.gov.ru/epz/order/notice/ok504/view/common-info.html?regNumber=0362200037225000020`

Несколько источников: `eis:https://zakupki.gov.ru/...,gpb:https://etpgpb.ru/...`

### Изменения по файлам

#### 3. `src/db/schema.py`
- Заменить `eis_url TEXT` на `source_urls TEXT` в DDL таблицы `tenders`

#### 4. `src/db/repository.py`
- `upsert_tender`: убрать параметр `eis_url`, добавить `source_urls: str | None = None`
- Добавить `update_tender_source_urls(conn, tender_id, source_urls)` — UPDATE-only

#### 5. `src/scraper/source_links.py` (новый файл)

```python
SOURCE_DOMAINS: dict[str, str] = {
    "zakupki.gov.ru": "eis",
}

async def extract_source_urls(page: Page) -> str | None:
    """Извлекает все внешние ссылки на источники со страницы тендера.
    Ищет все <a href="..."> на странице, фильтрует по SOURCE_DOMAINS.
    Возвращает строку 'eis:https://...,gpb:https://...' или None.
    """

def get_source_url(source_urls: str | None, source_name: str) -> str | None:
    """Извлекает URL конкретного источника из строки source_urls.
    
    get_source_url("eis:https://zakupki.gov.ru/...", "eis")
    → "https://zakupki.gov.ru/..."
    """

def parse_source_urls(source_urls: str | None) -> dict[str, str]:
    """Парсит строку source_urls в dict {name: url}.
    
    parse_source_urls("eis:https://zakupki.gov.ru/...,gpb:https://etpgpb.ru/...")
    → {"eis": "https://zakupki.gov.ru/...", "gpb": "https://etpgpb.ru/..."}
    """
```

#### 6. `src/scraper/active_tenders.py`
- `extract_inn_from_page` — возвращает `tuple[str | None, str | None]` `(inn, source_urls)`
- Внутри: после извлечения ИНН, вызывает `extract_source_urls(page)` и возвращает вторым элементом
- Убрать устаревший блок с `eis_link_el` (строки 322-328), заменён на `extract_source_urls`

#### 7. `src/scraper/eis_fallback.py`
- `fallback_extract_inn` — возвращает `tuple[str | None, str | None]` `(inn, source_urls)`
- Внутри: сохраняет найденный `eis_url` и возвращает как source_urls в формате `"eis:https://..."`

#### 8. `src/stages/search_active.py`
- Распаковывать `(inn, source_urls)` из `extract_inn_from_page` / `fallback_extract_inn`
- Объединять source_urls из обоих вызовов (если fallback тоже вызывался)
- Передавать `source_urls` в `upsert_tender`

#### 9. `src/parser/html_protocol.py`
- В `analyze_tender_protocol`: **всегда** вызывать `extract_source_urls(page)` после перехода на страницу тендера (строка 436-437)
- Вызывать `update_tender_source_urls(conn, tender_id, source_urls)` для сохранения
- Для EIS-фоллбэка: использовать `get_source_url(source_urls, "eis")` вместо `_try_get_eis_link(page)` (ссылка уже извлечена)
- Удалить `_try_get_eis_link` — заменена на `extract_source_urls` из `source_links.py`

#### 10. Тесты

- `test_active_tenders.py` — `TestExtractInnFromPage`: возврат кортежа `(inn, source_urls)`
- `test_eis_fallback.py` — `TestFallbackExtractInn`: возврат кортежа `(inn, source_urls)`
- `test_search_active_stage.py` — `upsert_tender` получает `source_urls`
- `test_html_protocol.py` — `extract_source_urls` вызывается, `update_tender_source_urls` вызывается, `_try_get_eis_link` удалён
- `test_repository.py` — новая функция `update_tender_source_urls`
- Новый `test_source_links.py` — тесты для `extract_source_urls`, `get_source_url`, `parse_source_urls`

#### 11. `STRUCTURE.md`
- Добавить `source_links.py` в секцию `scraper/`
- Обновить описание `eis_fallback.py`
- Обновить DDL-схему (`source_urls` вместо `eis_url`)

---

## Порядок выполнения

```
 1. Баг-фикс фильтра (historical_search.py, active_tenders.py)
 2. schema.py (source_urls вместо eis_url)
 3. repository.py (upsert_tender без eis_url, update_tender_source_urls)
 4. scraper/source_links.py (новый модуль)
 5. active_tenders.py (extract_inn_from_page → tuple)
 6. eis_fallback.py (fallback_extract_inn → tuple)
 7. search_active.py (передаёт source_urls)
 8. html_protocol.py (извлекает + сохраняет + использует для фоллбэка)
 9. Тесты
10. STRUCTURE.md
11. Прогон тестов
```
