# Обновлённый план: Rostender Parser

> Обновлено на основе ответов заказчика (19.02.2026)

## Решения по открытым вопросам

| # | Вопрос | Решение |
|---|--------|---------|
| 1 | Количество исторических тендеров | Последние **5** (настраиваемый параметр) |
| 2 | Неопределяемые тендеры | **Игнорировать** — не учитывать в статистике |
| 3 | Хранение документов | **Сохранять** локально, чистить при необходимости |
| 4 | Формат отчёта | **Excel** (.xlsx) + **консоль** |
| 5 | PDF-сканы | **Пропускать** (OCR пока не требуется) |

**Дополнительные уточнения:**
- Ключевые слова для поиска исторических закупок — **общие** из `SEARCH_KEYWORDS` (не из заголовка каждого тендера)
- Порог конкуренции — **настраиваемый** (по умолчанию 0.8, т.е. 4 из 5 достаточно)
- Word-отчёт **не нужен**, достаточно Excel
- roseltorg.ru — **исключён** из MVP, только rostender.info + zakupki.gov.ru

**Главный акцент заказчика:** качественный анализ прошедших закупок заказчика → выявление активных закупок с исторически низкой конкуренцией.

---

## 1. Структура проекта

```
rostender-parse/
├── TS_Q/                              # Спецификации
│
├── src/
│   ├── __init__.py
│   ├── main.py                        # Точка входа, CLI
│   ├── config.py                      # Настраиваемые параметры
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.py                  # DDL-схема БД
│   │   └── repository.py             # CRUD-операции (async)
│   │
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── browser.py                 # Управление Playwright
│   │   ├── active_tenders.py          # Модуль A: поиск активных тендеров
│   │   ├── historical_search.py       # Модуль B: поиск завершённых тендеров
│   │   └── eis_fallback.py            # Фоллбэк на zakupki.gov.ru
│   │
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── html_protocol.py           # Парсинг протоколов из HTML страницы
│   │   ├── docx_parser.py             # Парсинг .docx протоколов
│   │   └── pdf_parser.py              # Парсинг текстовых .pdf
│   │
│   ├── analyzer/
│   │   ├── __init__.py
│   │   └── competition.py             # Расчёт конкуренции
│   │
│   └── reporter/
│       ├── __init__.py
│       ├── console_report.py          # Вывод в консоль
│       └── excel_report.py            # Генерация .xlsx (openpyxl)
│
├── downloads/                         # Скачанные протоколы
│   └── {inn}/
│       └── {tender_id}/
│           └── protocol.docx
│
├── reports/                           # Готовые отчёты
│   └── report_2026-02-19.xlsx
│
├── data/
│   └── rostender.db                   # SQLite база
│
├── tests/
│   └── ...
│
├── pyproject.toml
└── README.md
```

---

## 2. Настраиваемые параметры (`config.py`)

```python
# --- Поиск активных тендеров ---
SEARCH_KEYWORDS = [
    "Поставка", "Поставки", "Поставке", "Закупка", "Снабжение",
    "Приобретение", "Оборудование и материалы", "Оборудование",
    "Станок", "Станки"
]

EXCLUDE_KEYWORDS = [
    "Выполнение работ", "Капитальный ремонт", "Оказание услуг",
    "Поставка лекарственных препаратов", "Благоустройство",
    "Предоставление субсидий", "Аренда", "Строительство",
    "Отбор получателей субсидии", "Возмещение",
    "Оказание консультационных услуг", "Лекарственного препарата",
    "Выполнение строительно-монтажных работ"
]

MIN_PRICE_ACTIVE = 25_000_000          # Мин. цена активных тендеров (Этап 1)
MIN_PRICE_RELATED = 2_000_000          # Мин. цена доп. тендеров заказчика (Этап 3)
MIN_PRICE_HISTORICAL = 1_000_000       # Мин. цена при поиске исторических (Этап 2)

# --- Анализ конкуренции ---
HISTORICAL_TENDERS_LIMIT = 5           # Кол-во последних завершённых для анализа
MAX_PARTICIPANTS_THRESHOLD = 2         # Макс. участников для "низкой конкуренции"
COMPETITION_RATIO_THRESHOLD = 0.8      # Доля тендеров с низкой конкуренцией (0.8 = 4 из 5)

# --- Хранение ---
KEEP_DOWNLOADED_DOCS = True            # Сохранять документы после анализа
CLEANUP_AFTER_DAYS = 30                # Через сколько дней чистить старые файлы

# --- Выход ---
OUTPUT_FORMATS = ["console", "excel"]  # Форматы выходных отчётов
```

---

## 3. Схема БД (SQLite)

```sql
-- Заказчики
CREATE TABLE IF NOT EXISTS customers (
    inn TEXT PRIMARY KEY,
    name TEXT,
    status TEXT DEFAULT 'new',           -- new | processing | analyzed | error
    last_analysis_date DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Тендеры (активные + исторические)
CREATE TABLE IF NOT EXISTS tenders (
    tender_id TEXT PRIMARY KEY,
    customer_inn TEXT NOT NULL,
    url TEXT,
    eis_url TEXT,
    title TEXT,
    price REAL,
    publish_date DATETIME,
    tender_status TEXT NOT NULL,          -- active | completed
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_inn) REFERENCES customers(inn)
);

-- Результаты парсинга протоколов
CREATE TABLE IF NOT EXISTS protocol_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id TEXT NOT NULL UNIQUE,
    participants_count INTEGER,           -- NULL = не удалось определить
    parse_source TEXT,                    -- html | docx | pdf_text | eis_html | eis_docx
    parse_status TEXT NOT NULL,           -- success | failed | skipped_scan | no_protocol
    doc_path TEXT,                        -- Путь к скачанному файлу
    notes TEXT,                           -- Доп. информация / причина ошибки
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tender_id) REFERENCES tenders(tender_id)
);

-- Итоговые результаты: интересные активные тендеры
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    active_tender_id TEXT NOT NULL,
    customer_inn TEXT NOT NULL,
    total_historical INTEGER,             -- Всего найдено завершённых
    total_analyzed INTEGER,               -- Успешно проанализировано (parse_status='success')
    total_skipped INTEGER,                -- Не удалось определить → игнорируются
    low_competition_count INTEGER,        -- С участниками ≤ порог
    competition_ratio REAL,               -- low_competition_count / total_analyzed
    is_interesting BOOLEAN DEFAULT 0,
    source TEXT DEFAULT 'primary',        -- primary | extended (Этап 3)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(active_tender_id) REFERENCES tenders(tender_id),
    FOREIGN KEY(customer_inn) REFERENCES customers(inn)
);
```

### Ключевое правило расчёта

Тендеры с `parse_status != 'success'` **не учитываются** при расчёте конкуренции:
- `total_analyzed` = только тендеры с `parse_status = 'success'`
- `total_skipped` = тендеры с `parse_status IN ('failed', 'skipped_scan', 'no_protocol')`
- `competition_ratio` = `low_competition_count / total_analyzed`
- Если `total_analyzed == 0` → заказчик неопределим, не считается интересным

---

## 4. Алгоритм работы

```
ЭТАП 1: Поиск активных тендеров
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  rostender.info → фильтры:
    - Ключевые слова: SEARCH_KEYWORDS
    - Цена: ≥ 25M руб.
    - Этап: "Приём заявок"
    - Скрывать без цены
    - Исключить: аукционы, закупки у единственного поставщика
  → Фильтрация заголовков: включить SEARCH_KEYWORDS, исключить EXCLUDE_KEYWORDS
  → Для каждого тендера: извлечь ИНН заказчика
  → Сохранить: tenders (active) + customers (new)
       │
       ▼
ЭТАП 2: Анализ истории заказчиков
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Для каждого customer (status='new'):

  2.1  Поиск завершённых тендеров на rostender.info:
       Фильтры: ИНН заказчика, "Завершён", цена ≥ 1M, SEARCH_KEYWORDS
       Взять последние HISTORICAL_TENDERS_LIMIT (5) штук

  2.2  Для каждого завершённого тендера → определить число участников:
       ┌─ Шаг 1: HTML-протокол на странице rostender.info
       ├─ Шаг 2: Скачать .docx/.doc → парсинг таблиц с участниками
       ├─ Шаг 3: Текстовый .pdf → regex-парсинг
       ├─ Шаг 4: Фоллбэк на zakupki.gov.ru (ЕИС) → HTML или документы
       └─ Шаг 5: PDF-скан или ничего → skipped (НЕ считается в статистике)

  2.3  Расчёт конкуренции:
       analyzed = кол-во с parse_status='success'
       low = кол-во где participants ≤ MAX_PARTICIPANTS_THRESHOLD (2)

       Если analyzed == 0 → неопределим, пропуск
       Если low / analyzed ≥ COMPETITION_RATIO_THRESHOLD (0.8) → ИНТЕРЕСНЫЙ
       │
       ▼
ЭТАП 3: Расширенный поиск по интересным заказчикам
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Для каждого интересного заказчика:
  → Найти ВСЕ его активные тендеры на rostender.info (цена ≥ 2M)
  → Фильтр заголовков по SEARCH_KEYWORDS
  → Для каждого нового активного тендера → ЭТАП 2 (анализ истории)
      Ключевые слова: общие SEARCH_KEYWORDS
  → Результаты сохраняются с source='extended'
       │
       ▼
ЭТАП 4: Формирование отчёта
━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Консоль:
    - Сводка: всего найдено / проанализировано / интересных
    - Список интересных тендеров

  Excel (.xlsx):
    - Лист 1 "Интересные тендеры": название, URL, цена, заказчик, ИНН,
      кол-во исторических, доля низкой конкуренции, source
    - Лист 2 "Все заказчики": ИНН, название, статус, кол-во активных тендеров
    - Лист 3 "Детали анализа": tender_id, заказчик, участники, источник парсинга,
      статус, путь к документу
```

---

## 5. Цепочка парсинга протоколов (приоритет)

Для каждого завершённого тендера последовательно пробуем:

| # | Источник | Метод | Результат |
|---|----------|-------|-----------|
| 1 | rostender.info HTML | Таблица "Протокол итогов" на странице тендера | Число участников |
| 2 | rostender.info Docs | Скачать .docx → поиск таблиц с "Участник" | Число участников |
| 3 | rostender.info Docs | Скачать текстовый .pdf → regex | Число участников |
| 4 | zakupki.gov.ru HTML | Перейти по ЕИС-ссылке → протокол на странице | Число участников |
| 5 | zakupki.gov.ru Docs | Скачать документы с ЕИС | Число участников |
| — | Ничего / PDF-скан | Логируем, `parse_status = skipped_scan` | **Игнорируется** |

---

## 6. Зависимости

```
playwright       — браузерная автоматизация (scraping)
aiosqlite        — async SQLite для хранения данных
python-docx      — парсинг .docx протоколов
pdfplumber       — парсинг текстовых PDF
openpyxl         — генерация Excel-отчётов
loguru           — структурированное логирование
```

---

## 7. Этапы разработки

| # | Этап | Описание | Файлы |
|---|------|----------|-------|
| 1 | Инфраструктура | pyproject.toml, config.py, БД, скелет main.py | `config.py`, `db/schema.py`, `db/repository.py`, `main.py` |
| 2 | Поиск активных тендеров | Скрейпинг rostender.info с фильтрами, извлечение ИНН | `scraper/browser.py`, `scraper/active_tenders.py` |
| 3 | Исторический поиск | Поиск завершённых тендеров по ИНН | `scraper/historical_search.py` |
| 4 | Парсинг протоколов | HTML, DOCX, PDF — извлечение числа участников | `parser/html_protocol.py`, `parser/docx_parser.py`, `parser/pdf_parser.py` |
| 5 | Фоллбэк ЕИС | zakupki.gov.ru — протоколы | `scraper/eis_fallback.py` |
| 6 | Анализатор | Расчёт метрик конкуренции, флаг "интересности" | `analyzer/competition.py` |
| 7 | Расширенный поиск | Доп. тендеры интересных заказчиков (≥ 2M) | Интеграция в `main.py` |
| 8 | Отчёты | Консоль + Excel | `reporter/console_report.py`, `reporter/excel_report.py` |
| 9 | Интеграция | Сквозной запуск, edge cases, тестирование | `main.py`, `tests/` |
