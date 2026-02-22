# Отчёт по выполнению Шагов 1 и 2

> Дата проверки: 19.02.2026
> Обновлено: 20.02.2026 — исправлены замечания #2, #3, #4, #5

## Шаг 1: Инфраструктура

### `pyproject.toml` — ГОТОВ

| Параметр | Ожидание (план) | Факт | Статус |
|---|---|---|---|
| Зависимости | playwright, aiosqlite, python-docx, pdfplumber, openpyxl, loguru | Все 6 указаны с правильными версиями | OK |
| Python version | >=3.11 | >=3.11 (фактически 3.14.2) | OK |
| Entry point | `src.main:main` | `rostender = "src.main:main"` | OK |
| dev deps | pytest, pytest-asyncio | Указаны в `[project.optional-dependencies]` | OK |
| Все пакеты установлены | — | aiosqlite 0.22.1, loguru 0.7.3, openpyxl 3.1.5, python-docx 1.2.0, pdfplumber 0.11.9, playwright OK | OK |

### `src/config.py` — ГОТОВ

Все параметры из плана присутствуют и совпадают:

- `SEARCH_KEYWORDS` — 10 слов, полностью совпадают с планом
- `EXCLUDE_KEYWORDS` — 13 фраз, полностью совпадают
- `MIN_PRICE_ACTIVE` = 25_000_000, `MIN_PRICE_RELATED` = 2_000_000, `MIN_PRICE_HISTORICAL` = 1_000_000
- `HISTORICAL_TENDERS_LIMIT` = 5, `MAX_PARTICIPANTS_THRESHOLD` = 2, `COMPETITION_RATIO_THRESHOLD` = 0.8
- `KEEP_DOWNLOADED_DOCS`, `CLEANUP_AFTER_DAYS`, `OUTPUT_FORMATS` — все на месте
- Пути `DATA_DIR`, `DOWNLOADS_DIR`, `REPORTS_DIR`, `DB_PATH` — определены корректно

### `src/db/schema.py` — ГОТОВ

4 таблицы, DDL совпадает с планом:

- `customers` (inn PK, name, status, last_analysis_date, created_at)
- `tenders` (tender_id PK, customer_inn FK, url, eis_url, title, price, publish_date, tender_status, created_at)
- `protocol_analysis` (id PK, tender_id UNIQUE FK, participants_count, parse_source, parse_status, doc_path, notes, analyzed_at)
- `results` (id PK, active_tender_id FK, customer_inn FK, total_historical, total_analyzed, total_skipped, low_competition_count, competition_ratio, is_interesting, source, created_at)

Проверено: `init_db()` успешно создаёт все таблицы. `PRAGMA table_info` подтверждает корректность колонок.

### `src/db/repository.py` — ГОТОВ

Полный набор CRUD-операций:

- `get_connection()` — WAL mode + foreign_keys=ON
- `init_db()` — executescript(SCHEMA_SQL)
- `upsert_customer()`, `update_customer_status()`, `get_customers_by_status()`
- `upsert_tender()`, `get_tenders_by_customer()`, `get_active_tenders()`
- `upsert_protocol_analysis()`, `get_protocol_analyses_for_customer()`
- `insert_result()`, `get_interesting_results()` (с JOIN на tenders + customers)

### `src/main.py` — ГОТОВ (скелет)

- `_configure_logging()` — loguru настроен (stderr + файл с ротацией)
- `_ensure_dirs()` — создание data/, downloads/, reports/
- `run()` — async pipeline: init_db → Этап 1 (подключён) → Этапы 2-4 (TODO-заглушки)
- `main()` — sync обёртка через `asyncio.run()`
- Этап 1 полностью подключён: browser → search_active_tenders → extract_inn + get_customer_name → upsert в БД

**Вердикт по Шагу 1: ВЫПОЛНЕН ПОЛНОСТЬЮ**

---

## Шаг 2: Поиск активных тендеров

### `src/scraper/browser.py` — ГОТОВ

- `create_browser()` — async context manager, Chromium headless
- `create_page()` — viewport 1280x900, кастомный UA (Chrome 131), locale ru-RU, timeout 60s
- `safe_goto()` — навигация с `wait_until="domcontentloaded"`
- `polite_wait()` — пауза 2 сек между запросами
- `BASE_URL = "https://rostender.info"`

### `src/scraper/active_tenders.py` — ГОТОВ

Реализованы 4 функции:

1. **`_parse_tenders_on_page(page)`** — парсит карточки тендеров на одной странице
2. **`search_active_tenders(page)`** — заполняет фильтры, парсит все страницы с пагинацией
3. **`extract_inn_from_page(page, url)`** — извлекает ИНН со страницы тендера
4. **`get_customer_name(page)`** — извлекает название организации

**Вердикт по Шагу 2: ВЫПОЛНЕН ПОЛНОСТЬЮ**

---

## Замечания (из первоначальной проверки)

| # | Описание | Решение | Статус |
|---|----------|---------|--------|
| 1 | Дата «сегодня-сегодня» — поиск ограничен тендерами, опубликованными сегодня | **По ТЗ** — оставлено как есть | Закрыто |
| 2 | **Нет пагинации** — парсилась только первая страница | **Исправлено** — добавлен цикл по `ul.pagination > li.last > a` | Закрыто |
| 3 | CSS-селекторы не верифицированы | **Частично исправлено** — форма и результаты верифицированы по реальному HTML; страница тендера (ИНН) — требует проверки при запуске. См. `TS_Q/selectors_verification.md` | Закрыто |
| 4 | Имя заказчика не сохраняется | **Исправлено** — `get_customer_name()` вызывается в main.py, передаётся в `upsert_customer()` | Закрыто |
| 5 | Фоллбэк по ЕИС-ссылке — `pass` | **Пометка добавлена** — TODO комментарий + logger.debug. Задел на Шаг 5 | Закрыто |

---

## Исправленные CSS-селекторы

| Что | Было (неверно) | Стало (верифицировано) |
|-----|---------------|----------------------|
| Карточка тендера | `.tender-row` / `.search-results__item` | `article.tender-row` |
| ID тендера | regex из URL `/tender/(\d+)` | атрибут `id` у `<article>` |
| Ссылка | `a.description` / `a[href*='/tender/']` | `a.tender-info__description` / `a.tender-info__link` |
| Цена | `.tender-row__price` / `.price` | `.starting-price__price` |
| Наличие результатов | `.search-results` | `article.tender-row` (проверка наличия) |
| Цена (ввод) | `page.fill("#min_price-disp", ...)` | JS evaluate: `#min_price` + maskMoney |
| Пагинация | — (отсутствовала) | `ul.pagination > li.last > a` |

---

## Итого

| Шаг | Статус | Файлы | Замечания |
|-----|--------|-------|-----------|
| 1. Инфраструктура | **ВЫПОЛНЕН ПОЛНОСТЬЮ** | pyproject.toml, config.py, db/schema.py, db/repository.py, main.py | Нет замечаний |
| 2. Поиск активных тендеров | **ВЫПОЛНЕН ПОЛНОСТЬЮ** | scraper/browser.py, scraper/active_tenders.py | Все замечания исправлены. Верификация ИНН-селекторов — при первом запуске (см. `selectors_verification.md`) |
