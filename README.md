# Rostender Parser

CLI-инструмент для автоматического поиска и анализа государственных тендеров на портале rostender.info. Система находит активные тендеры, анализирует историю заказчиков и выявляет тендеры с низкой конкуренцией.

## Установка

Рекомендуется использовать [uv](https://github.com/astral-sh/uv) для быстрого управления зависимостями и окружением.

```bash
uv pip install -e .
```

После установки нужно установить браузер Playwright:

```bash
uv run playwright install chromium
```

## Конфигурация
...
### CLI-аргументы

Параметры из `config.yaml` можно переопределить через командную строку:

```bash
uv run rostender --keywords Поставка Оборудование --min-price 10000000 --days-back 14
```
...
## Использование

### Полный пайплайн

```bash
# Запуск всех этапов (1-4) в одной браузерной сессии
uv run rostender
uv run rostender run

# Или напрямую
uv run python -m src.main

# Проверить параметры без запуска
uv run rostender --dry-run
```
...
### Примеры

```bash
# Поиск за последние 14 дней с порогом цены 10M
uv run rostender --days-back 14 --min-price 10000000

# Только поиск активных с кастомными ключевыми словами
uv run rostender search-active -k Поставка Оборудование --min-price 10000000

# Перегенерировать основной отчёт по уже собранным данным
uv run rostender report

# Сгенерировать список активных тендеров из БД
uv run rostender report-active
```

## Архитектура
...
    ├── scraper/             # Веб-скрейпинг
    │   ├── auth.py          # Авторизация на rostender.info
    │   ├── browser.py       # Управление Playwright-браузером
    │   ├── active_tenders.py
    │   ├── historical_search.py
    │   ├── unified_fallback.py # Единый диспетчер фоллбэков
    │   └── fallbacks/       # Модульная система фоллбэков
    │       ├── base.py      # Базовый класс стратегии
    │       ├── eis.py       # Стратегия для ЕИС (zakupki.gov.ru)
    │       └── ...
...
## Тесты

```bash
uv run pytest tests/
```


После установки нужно установить браузер Playwright:

```bash
playwright install chromium
```

## Конфигурация

Все настройки хранятся в файле `config.yaml` в корне проекта.

### Первоначальная настройка

```bash
# Скопируйте шаблон конфигурации
cp config.yaml.example config.yaml

# Заполните логин и пароль от rostender.info
```

### Параметры config.yaml

| Параметр | Описание | Значение по умолчанию |
|----------|----------|-----------------------|
| `rostender_login` | Логин на rostender.info | *обязательно* |
| `rostender_password` | Пароль на rostender.info | *обязательно* |
| `search_keywords` | Ключевые слова для поиска тендеров | Список из 11 слов |
| `exclude_keywords` | Исключаемые слова | Список из 13 фраз |
| `search_date_from` / `search_date_to` | Диапазон дат (DD.MM.YYYY) | `null` (сегодня) |
| `min_price_active` | Мин. цена активных тендеров (Этап 1) | 25 000 000 |
| `min_price_related` | Мин. цена доп. тендеров заказчика (Этап 3) | 2 000 000 |
| `min_price_historical` | Мин. цена исторических тендеров (Этап 2) | 1 000 000 |
| `historical_tenders_limit` | Кол-во завершённых тендеров для анализа | 5 |
| `max_participants_threshold` | Порог участников для «низкой конкуренции» | 2 |
| `competition_ratio_threshold` | Доля тендеров с низкой конкуренцией | 0.8 |
| `keep_downloaded_docs` | Сохранять документы после анализа | `true` |
| `cleanup_after_days` | Через сколько дней чистить файлы | 30 |
| `output_formats` | Форматы вывода | `[console, excel]` |

> **Важно:** файл `config.yaml` содержит учётные данные и добавлен в `.gitignore`. В git коммитится только шаблон `config.yaml.example`.

### CLI-аргументы

Параметры из `config.yaml` можно переопределить через командную строку:

```bash
rostender --keywords Поставка Оборудование --min-price 10000000 --days-back 14
```

| Аргумент | Описание |
|----------|----------|
| `--keywords`, `-k` | Ключевые слова для поиска |
| `--min-price`, `-p` | Мин. цена активных тендеров |
| `--min-price-related` | Мин. цена для расширенного поиска |
| `--min-price-historical` | Мин. цена для исторического поиска |
| `--history-limit`, `-l` | Кол-во завершённых тендеров для анализа |
| `--max-participants`, `-m` | Макс. участников для низкой конкуренции |
| `--ratio-threshold`, `-r` | Доля тендеров с низкой конкуренцией |
| `--date-from` | Дата поиска ОТ (DD.MM.YYYY) |
| `--date-to` | Дата поиска ДО (DD.MM.YYYY) |
| `--days-back`, `-d` | Искать за последние N дней (по умолчанию 7) |
| `--dry-run` | Показать параметры без запуска браузера |

## Использование

### Полный пайплайн

```bash
# Запуск всех этапов (1-4) в одной браузерной сессии
rostender
rostender run

# Или напрямую
python -m src.main

# Проверить параметры без запуска
rostender --dry-run
```

### Запуск отдельных этапов

Каждый этап можно запускать независимо. Этапы обмениваются данными через SQLite — результаты предыдущего этапа сохраняются в БД и читаются следующим.

```bash
rostender search-active          # Этап 1: Поиск активных тендеров + извлечение ИНН
rostender report-active          # Генерация списка активных тендеров (отчёт из Этапа 1)
rostender analyze-history        # Этап 2: Анализ истории заказчиков
rostender extended-search        # Этап 3: Расширенный поиск по интересным заказчикам
rostender report                 # Этап 4: Генерация отчёта (без браузера)
```

### Примеры

```bash
# Поиск за последние 14 дней с порогом цены 10M
rostender --days-back 14 --min-price 10000000

# Только поиск активных с кастомными ключевыми словами
rostender search-active -k Поставка Оборудование --min-price 10000000

# Перегенерировать основной отчёт по уже собранным данным
rostender report

# Сгенерировать список активных тендеров из БД
rostender report-active
```

## Архитектура

```
├── config.yaml.example  # Шаблон конфигурации
├── config.yaml          # Конфигурация (не в git)
├── pyproject.toml       # Зависимости и метаданные
├── data/                # БД и логи
├── downloads/           # Скачанные протоколы
├── reports/             # Сгенерированные отчёты
│
└── src/
    ├── main.py              # CLI-диспетчер с субкомандами
    ├── config.py            # Загрузка конфигурации из config.yaml
    ├── stages/              # Этапы пайплайна (запускаются независимо)
    │   ├── params.py        # PipelineParams — общие параметры
    │   ├── search_active.py # Этап 1: Поиск активных тендеров
    │   ├── analyze_history.py # Этап 2: Анализ истории
    │   ├── extended_search.py # Этап 3: Расширенный поиск
    │   └── report.py       # Этап 4: Генерация отчёта
    ├── scraper/             # Веб-скрейпинг
    │   ├── auth.py          # Авторизация на rostender.info
    │   ├── browser.py       # Управление Playwright-браузером
    │   ├── active_tenders.py
    │   ├── historical_search.py
    │   └── eis_fallback.py
    ├── parser/              # Парсинг документов
    │   ├── html_protocol.py
    │   ├── pdf_parser.py
    │   ├── docx_parser.py
    │   └── participant_patterns.py
    ├── analyzer/            # Анализ конкуренции
    │   └── competition.py
    ├── db/                  # База данных (SQLite)
    │   ├── schema.py
    │   └── repository.py
    └── reporter/            # Генерация отчётов
        ├── console_report.py
        ├── excel_report.py
        └── active_tenders_report.py # Отчёт по активным тендерам
```

## Пайплайн

При запуске полного пайплайна (`rostender` / `rostender run`) все этапы выполняются в рамках одной браузерной сессии (один логин). При запуске отдельного этапа создаётся собственная сессия.

| Команда | Этап | Браузер | Описание |
|---------|------|---------|----------|
| `rostender search-active` | 1 | да | Поиск активных тендеров, извлечение ИНН заказчиков + сохранение Excel-списка |
| `rostender report-active` | - | нет | Генерация Excel-списка активных тендеров из БД |
| `rostender analyze-history` | 2 | да | Поиск завершённых тендеров, парсинг протоколов, расчёт метрик |
| `rostender extended-search` | 3 | да | Дополнительные тендеры по интересным заказчикам |
| `rostender report` | 4 | нет | Генерация отчёта (Excel + консоль) по данным из БД |

Этапы обмениваются данными через SQLite:

```
Этап 1 → customers(new), tenders(active)
              ↓
Этап 2 → tenders(completed), protocol_analysis, results(primary)
              ↓
Этап 3 → tenders, protocol_analysis, results(extended)
              ↓
Этап 4 → читает все таблицы → Excel + консоль
```

## Зависимости

- **playwright** — Браузерная автоматизация
- **aiosqlite** — Асинхронный SQLite
- **openpyxl** — Генерация Excel
- **pdfplumber** — Извлечение текста из PDF
- **python-docx** — Парсинг DOCX
- **loguru** — Логирование
- **pyyaml** — Загрузка конфигурации

## Тесты

```bash
pytest tests/
```

## Сессии и Изоляция Данных

Rostender использует уникальные ID сессий (`Session ID`) для изоляции запусков.

### Как это работает
При каждом запуске создаётся уникальный `Session ID` (формат: `YYYYMMDD-HHMMSS-xxxxxx`).
Все данные, созданные в рамках одного запуска, связываются с этим ID:
- Тендеры и заказчики (`tenders`, `customers`)
- Результаты анализа (`results`)
- Протоколы (`protocol_analysis`)

### Архивация
Перед каждым запуском (команда `run`, `search-active` и т.д.) данные предыдущего запуска автоматически перемещаются в архивные таблицы (`tenders_archive`, `customers_archive`). Это обеспечивает:
- **Изоляцию данных**: Результаты разных запусков не смешиваются.
- **Идемпотентность**: Повторный запуск с теми же параметрами перезапишет активные данные.
- **Аудит**: Старые данные сохраняются в архиве.

### Отчёты
Отчёты Excel именуются уникально по ID сессии: `report_[SessionID]_[Stage].xlsx`.
Это позволяет легко находить отчёты конкретного запуска.

### Очистка БД
Для полной очистки базы данных (включая архивы):
```bash
uv run rostender clean-db
```
