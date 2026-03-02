# Rostender Parser — План рефакторинга: независимый запуск этапов

## Цель

Рефакторинг `main.py` так, чтобы каждый этап pipeline можно было запускать отдельно через CLI-субкоманды. Полный pipeline (`rostender` без аргументов) остаётся поведением по умолчанию для обратной совместимости.

---

## Текущее состояние

### Проблема

`src/main.py` содержит монолитную функцию `run()` (~470 строк), в которой все 4 этапа выполняются последовательно внутри одного блока `async with create_browser()`. Невозможно:

- Запустить только поиск активных тендеров (Этап 1)
- Перезапустить анализ истории (Этап 2) без повторного поиска
- Сгенерировать отчёт (Этап 4) без запуска браузера
- Отладить отдельный этап изолированно

### Что работает в нашу пользу

- **БД как контракт между этапами** — каждый этап читает из SQLite и пишет в SQLite. Передача данных между этапами через in-memory переменные минимальна.
- **Модули уже разделены** — `scraper/`, `parser/`, `analyzer/`, `db/`, `reporter/` — чистые модули с отдельной ответственностью.
- **Этапы последовательны** — Этап 2 зависит от данных Этапа 1 в БД, Этап 3 от Этапа 2 и т.д.

---

## Целевой CLI-интерфейс

```bash
# Полный pipeline (обратная совместимость)
rostender
rostender run

# Отдельные этапы
rostender search-active        # Этап 1: Поиск активных тендеров + извлечение ИНН
rostender analyze-history      # Этап 2: Поиск завершённых тендеров + парсинг протоколов + метрики
rostender extended-search      # Этап 3: Расширенный поиск по интересным заказчикам
rostender report               # Этап 4: Генерация отчёта (без браузера)

# Все существующие флаги работают с любой субкомандой
rostender search-active --keywords Поставка Оборудование --min-price 10000000 --days-back 14
rostender report               # Только отчёт по уже собранным данным
rostender --dry-run             # Показать параметры без запуска
```

---

## Новая файловая структура

```
src/
├── __init__.py
├── config.py                  # БЕЗ ИЗМЕНЕНИЙ
├── main.py                    # РЕФАКТОРИНГ: тонкий диспетчер (~150 строк)
│
├── stages/                    # НОВЫЙ ПАКЕТ
│   ├── __init__.py            # Экспорт всех stage-функций
│   ├── params.py              # PipelineParams dataclass + фабрика from_args()
│   ├── search_active.py       # Этап 1
│   ├── analyze_history.py     # Этап 2
│   ├── extended_search.py     # Этап 3
│   └── report.py              # Этап 4
│
├── scraper/                   # БЕЗ ИЗМЕНЕНИЙ
├── parser/                    # БЕЗ ИЗМЕНЕНИЙ
├── analyzer/                  # БЕЗ ИЗМЕНЕНИЙ
├── db/                        # БЕЗ ИЗМЕНЕНИЙ
└── reporter/                  # БЕЗ ИЗМЕНЕНИЙ
```

---

## Пошаговый план реализации

### Шаг 1: Создать `src/stages/__init__.py`

Пустой файл инициализации пакета.

```python
"""Этапы pipeline Rostender Parser."""
```

---

### Шаг 2: Создать `src/stages/params.py` — общие параметры

**Что содержит:**

```python
@dataclass
class PipelineParams:
    keywords: list[str]
    min_price_active: int
    min_price_related: int
    min_price_historical: int
    history_limit: int
    max_participants: int
    ratio_threshold: float
    date_from: str | None
    date_to: str | None
    output_formats: list[str]
```

**Фабричный метод:**

```python
@staticmethod
def from_args(args: argparse.Namespace) -> PipelineParams:
    """Создаёт PipelineParams, объединяя CLI-аргументы и значения из config.yaml."""
```

Этот метод содержит логику из текущего `main.py:197-224` — резолвинг значений CLI args vs дефолты из `config.py`.

**Откуда берётся код:** Перенос строк 197-224 из `src/main.py` (блок определения `keywords`, `min_price_active`, `min_price_related`, и т.д.).

---

### Шаг 3: Создать `src/stages/search_active.py` — Этап 1

**Функция:**

```python
async def run_search_active(page: Page, params: PipelineParams) -> None:
    """Этап 1: Поиск активных тендеров, извлечение ИНН, сохранение в БД."""
```

**Откуда берётся код:** Перенос строк 256-300 из `src/main.py`:

- Поиск активных тендеров через `search_active_tenders()`
- Цикл по найденным тендерам:
  - Извлечение ИНН через `extract_inn_from_page()` + `fallback_extract_inn()`
  - Извлечение имени заказчика через `get_customer_name()`
  - Сохранение в БД: `upsert_customer()`, `upsert_tender()`

**Импорты:**
- `src.scraper.active_tenders`: `extract_inn_from_page`, `get_customer_name`, `search_active_tenders`
- `src.scraper.eis_fallback`: `fallback_extract_inn`
- `src.db.repository`: `get_connection`, `upsert_customer`, `upsert_tender`

**Зависимости данных:** Нет (начальный этап).

---

### Шаг 4: Создать `src/stages/analyze_history.py` — Этап 2

**Функция:**

```python
async def run_analyze_history(page: Page, params: PipelineParams) -> None:
    """Этап 2: Поиск завершённых тендеров по ИНН, парсинг протоколов, расчёт метрик."""
```

**Откуда берётся код:** Перенос строк 302-448 из `src/main.py`:

- Получение заказчиков со статусом `new`
- Для каждого заказчика:
  - Обновление статуса → `processing`
  - Получение активных тендеров из БД
  - Для каждого активного тендера:
    - Извлечение ключевых слов из заголовка
    - Поиск завершённых тендеров
    - Сохранение завершённых тендеров в БД
    - Парсинг протоколов через `analyze_tender_protocol()`
    - Расчёт метрик через `calculate_metrics()`
    - Сохранение результатов через `insert_result()`
  - Обновление статуса → `analyzed` / `error`

**Импорты:**
- `src.scraper.historical_search`: `search_historical_tenders`, `extract_keywords_from_title`
- `src.parser.html_protocol`: `analyze_tender_protocol`
- `src.analyzer.competition`: `calculate_metrics`, `log_metrics`
- `src.db.repository`: `get_connection`, `get_customers_by_status`, `get_tenders_by_customer`, `update_customer_status`, `upsert_tender`, `get_latest_protocol_analyses`, `insert_result`, `result_exists`

**Зависимости данных:** Требует, чтобы в БД были заказчики со статусом `new` (создаёт Этап 1).

---

### Шаг 5: Создать `src/stages/extended_search.py` — Этап 3

**Функция:**

```python
async def run_extended_search(page: Page, params: PipelineParams) -> None:
    """Этап 3: Расширенный поиск по интересным заказчикам."""
```

**Откуда берётся код:** Перенос строк 450-632 из `src/main.py`:

- Получение интересных заказчиков из БД
- Для каждого заказчика:
  - Поиск активных тендеров по ИНН (цена ≥ `min_price_related`)
  - Обновление статуса → `extended_processing`
  - Для каждого нового тендера:
    - Проверка дублей через `tender_exists()` и `result_exists()`
    - Сохранение нового тендера
    - Поиск завершённых тендеров по ключевым словам из заголовка
    - Парсинг протоколов
    - Расчёт метрик
    - Сохранение результатов (source=`extended`)
  - Обновление статуса → `extended_analyzed`

**Импорты:**
- `src.scraper.active_tenders`: `search_tenders_by_inn`
- `src.scraper.historical_search`: `search_historical_tenders`, `extract_keywords_from_title`
- `src.parser.html_protocol`: `analyze_tender_protocol`
- `src.analyzer.competition`: `calculate_metrics`, `log_metrics`
- `src.db.repository`: `get_connection`, `get_interesting_customers`, `update_customer_status`, `tender_exists`, `result_exists`, `upsert_tender`, `get_latest_protocol_analyses`, `insert_result`

**Зависимости данных:** Требует результаты с `is_interesting=True` в таблице `results` (создаёт Этап 2).

---

### Шаг 6: Создать `src/stages/report.py` — Этап 4

**Функция:**

```python
async def run_report(params: PipelineParams) -> None:
    """Этап 4: Генерация отчётов. Браузер НЕ нужен."""
```

**Откуда берётся код:** Перенос строк 634-651 из `src/main.py`:

- Чтение данных из БД:
  - `get_interesting_results()`
  - `get_all_results()`
  - `get_all_customers()`
  - `get_all_protocol_analyses()`
- Генерация console-отчёта (если `console` в `output_formats`)
- Генерация Excel-отчёта (если `excel` в `output_formats`)

**Импорты:**
- `src.db.repository`: `get_connection`, `get_interesting_results`, `get_all_results`, `get_all_customers`, `get_all_protocol_analyses`
- `src.reporter.console_report`: `print_console_report`, `log_console_summary`
- `src.reporter.excel_report`: `generate_excel_report`

**Зависимости данных:** Требует данные в БД (создают Этапы 1-3). Может запускаться в любой момент для генерации отчёта по текущему состоянию БД.

**Особенность:** Не принимает `page` — браузер не нужен.

---

### Шаг 7: Рефакторинг `src/main.py` — тонкий диспетчер

**Итоговый размер:** ~150 строк (вместо ~663).

**Структура:**

```python
# 1. _configure_logging() — без изменений (строки 64-82)
# 2. _ensure_dirs() — без изменений (строки 85-88)
# 3. _parse_args() — ПЕРЕПИСАТЬ: добавить subparsers
# 4. run() — ПЕРЕПИСАТЬ: диспетчер
# 5. main() — без изменений (строки 656-658)
```

**Новый `_parse_args()`:**

```python
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rostender Parser — поиск и анализ тендеров",
    )

    # Общие аргументы (на верхнем уровне — доступны всем субкомандам)
    _add_common_args(parser)

    # Субкоманды
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Полный pipeline (по умолчанию)")
    _add_common_args(run_parser)

    s1 = subparsers.add_parser("search-active", help="Этап 1: Поиск активных тендеров")
    _add_common_args(s1)

    s2 = subparsers.add_parser("analyze-history", help="Этап 2: Анализ истории заказчиков")
    _add_common_args(s2)

    s3 = subparsers.add_parser("extended-search", help="Этап 3: Расширенный поиск")
    _add_common_args(s3)

    s4 = subparsers.add_parser("report", help="Этап 4: Генерация отчёта")
    _add_common_args(s4)

    args = parser.parse_args()

    # Если субкоманда не указана — полный pipeline
    if args.command is None:
        args.command = "run"

    return args


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Добавляет общие аргументы к парсеру."""
    parser.add_argument("--keywords", "-k", nargs="+", default=None, ...)
    parser.add_argument("--min-price", "-p", type=int, default=None, ...)
    parser.add_argument("--min-price-related", type=int, default=None, ...)
    parser.add_argument("--min-price-historical", type=int, default=None, ...)
    parser.add_argument("--history-limit", "-l", type=int, default=None, ...)
    parser.add_argument("--max-participants", "-m", type=int, default=None, ...)
    parser.add_argument("--ratio-threshold", "-r", type=float, default=None, ...)
    parser.add_argument("--date-from", type=str, default=None, ...)
    parser.add_argument("--date-to", type=str, default=None, ...)
    parser.add_argument("--days-back", "-d", type=int, default=7, ...)
    parser.add_argument("--dry-run", action="store_true", ...)
```

**Новый `run()`:**

```python
async def run() -> None:
    args = _parse_args()
    params = PipelineParams.from_args(args)

    _configure_logging()
    _ensure_dirs()

    logger.info("=== Rostender Parser запущен ===")
    logger.info("Команда: {}, параметры: keywords={}, min_price={}, ...",
                args.command, len(params.keywords), params.min_price_active, ...)

    if args.dry_run:
        logger.info("DRY RUN: параметры показаны, выход")
        return

    await init_db()

    command = args.command

    if command == "run":
        # Полный pipeline: один браузер, одна сессия
        async with create_browser() as browser:
            async with create_page(browser) as page:
                await login(page)
                await run_search_active(page, params)
                await run_analyze_history(page, params)
                await run_extended_search(page, params)
        await run_report(params)

    elif command == "report":
        # Отчёт: браузер не нужен
        await run_report(params)

    elif command in ("search-active", "analyze-history", "extended-search"):
        # Отдельный этап: собственная браузерная сессия
        async with create_browser() as browser:
            async with create_page(browser) as page:
                await login(page)
                if command == "search-active":
                    await run_search_active(page, params)
                elif command == "analyze-history":
                    await run_analyze_history(page, params)
                elif command == "extended-search":
                    await run_extended_search(page, params)

    logger.info("=== Rostender Parser завершён ===")
```

---

### Шаг 8: Обновить `STRUCTURE.md`

Обновить секции:
- **File Structure** — добавить пакет `stages/`
- **Processing Pipeline** — добавить информацию о CLI-субкомандах
- **Usage** — добавить примеры запуска отдельных этапов

---

### Шаг 9: Запустить тесты

```bash
python -m pytest tests/ -v
```

Убедиться, что существующие тесты проходят. Тесты покрывают `participant_patterns.py`, `competition.py` и `repository.py` — они не затронуты рефакторингом.

---

## Таблица соответствия: старый код → новый

| Строки `main.py` (до) | Куда переносится | Описание |
|------------------------|------------------|----------|
| 1-61 | `main.py` (остаётся) | Импорты — сокращаются |
| 64-88 | `main.py` (остаётся) | `_configure_logging()`, `_ensure_dirs()` |
| 91-180 | `main.py` (переписывается) | `_parse_args()` → с subparsers |
| 183-190 | `stages/params.py` | `_resolve_dates()` → в `PipelineParams.from_args()` |
| 193-248 | `main.py` (переписывается) | `run()` → тонкий диспетчер |
| 256-300 | `stages/search_active.py` | Этап 1: поиск активных тендеров |
| 302-448 | `stages/analyze_history.py` | Этап 2: анализ истории |
| 450-632 | `stages/extended_search.py` | Этап 3: расширенный поиск |
| 634-651 | `stages/report.py` | Этап 4: отчёты |
| 656-662 | `main.py` (остаётся) | `main()`, `__main__` |

---

## Что НЕ меняется

| Модуль | Причина |
|--------|---------|
| `src/config.py` | Только читает конфиг, не зависит от pipeline |
| `src/scraper/*.py` | Чистые функции, принимают `page` — без изменений |
| `src/parser/*.py` | Чистые функции парсинга документов |
| `src/analyzer/*.py` | Чистые функции расчёта метрик |
| `src/db/*.py` | CRUD-операции, не зависят от pipeline |
| `src/reporter/*.py` | Генерация отчётов, не зависят от pipeline |
| `pyproject.toml` | Entry point `rostender = "src.main:main"` — без изменений |
| `tests/*.py` | Тестируют внутренние модули, не `main.py` |

---

## Диаграмма зависимостей этапов

```
┌─────────────────┐
│   config.yaml   │
│   + CLI args    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PipelineParams  │  (stages/params.py)
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────┐
│ Этап 1:         │────▶│  SQLite  │  customers(status=new), tenders(status=active)
│ search_active   │     │          │
└─────────────────┘     │          │
                        │          │
┌─────────────────┐     │          │
│ Этап 2:         │◀───▶│          │  Читает: customers(new), tenders(active)
│ analyze_history │     │          │  Пишет: tenders(completed), protocol_analysis, results
└─────────────────┘     │          │
                        │          │
┌─────────────────┐     │          │
│ Этап 3:         │◀───▶│          │  Читает: results(is_interesting=true)
│ extended_search │     │          │  Пишет: tenders, protocol_analysis, results(source=extended)
└─────────────────┘     │          │
                        │          │
┌─────────────────┐     │          │
│ Этап 4:         │◀────│          │  Читает: все таблицы
│ report          │     └──────────┘  Пишет: файлы отчётов (console, xlsx)
└─────────────────┘
```

---

## Браузерные сессии

### Полный pipeline (`rostender` / `rostender run`)

```
Browser ──┐
  Page ───┤
  Login ──┤
          ├── Этап 1 (search_active)
          ├── Этап 2 (analyze_history)
          ├── Этап 3 (extended_search)
          └── [закрываем браузер]
              Этап 4 (report) — без браузера
```

1 запуск браузера, 1 логин. Максимальная эффективность.

### Отдельный этап (`rostender search-active`)

```
Browser ──┐
  Page ───┤
  Login ──┤
          └── Этап 1 (search_active)
              [закрываем браузер]
```

Собственная сессия. Требует отдельный логин.

### Отчёт (`rostender report`)

```
Этап 4 (report) — без браузера, только БД → файлы
```

---

## Риски и миграция

| Риск | Митигация |
|------|-----------|
| Пользователь запускает Этап 2 без Этапа 1 | В логах будет: "Заказчиков со статусом 'new': 0". Это уже существующее поведение. |
| Пользователь запускает Этап 3 без Этапа 2 | В логах: "Интересных заказчиков: 0". Тоже уже работает. |
| Параллельный запуск этапов | SQLite поддерживает WAL-режим. Но мы **не рекомендуем** параллельный запуск и не гарантируем корректность. |
| Обратная совместимость | `rostender` без аргументов = полный pipeline. Все существующие CLI-флаги работают. |

---

## Порядок коммитов

1. **Коммит 1:** Добавить `src/stages/` пакет с `params.py` (PipelineParams)
2. **Коммит 2:** Добавить `stages/search_active.py`, `stages/analyze_history.py`, `stages/extended_search.py`, `stages/report.py`
3. **Коммит 3:** Рефакторинг `main.py` — переход на диспетчер с субкомандами
4. **Коммит 4:** Обновить `STRUCTURE.md`
5. **Коммит 5:** Прогнать тесты, исправить если нужно
