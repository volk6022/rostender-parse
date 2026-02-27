# Rostender Parser

CLI-инструмент для автоматического поиска и анализа государственных тендеров на портале rostender.info. Система находит активные тендеры, анализирует историю заказчиков и выявляет тендеры с низкой конкуренцией.

## Установка

```bash
pip install -e .
```

## Использование

```bash
# Запуск полного пайплайна
python -m src.main

# Или через команду
rostender
```

## Конфигурация

Настройки находятся в `src/config.py`:

| Параметр | Описание | Значение |
|----------|----------|----------|
| `SEARCH_KEYWORDS` | Ключевые слова для поиска тендеров | Список |
| `EXCLUDE_KEYWORDS` | Исключаемые слова | Список |
| `MIN_PRICE_ACTIVE` | Мин. цена активных тендеров | 25M |
| `MIN_PRICE_RELATED` | Мин. цена связанных тендеров | 2M |
| `HISTORICAL_TENDERS_LIMIT` | Лимит исторических тендеров | 50 |
| `MAX_PARTICIPANTS_THRESHOLD` | Порог участников | 2 |
| `COMPETITION_RATIO_THRESHOLD` | Порог конкуренции | 0.8 |

## Архитектура

```
src/
├── main.py              # Точка входа (CLI)
├── config.py            # Конфигурация
├── scraper/             # Веб-скрейпинг
│   ├── browser.py
│   ├── active_tenders.py
│   ├── historical_search.py
│   └── eis_fallback.py
├── parser/             # Парсинг документов
│   ├── html_protocol.py
│   ├── pdf_parser.py
│   ├── docx_parser.py
│   └── participant_patterns.py
├── analyzer/           # Анализ конкуренции
│   └── competition.py
├── db/                 # База данных
│   ├── schema.py
│   └── repository.py
└── reporter/           # Генерация отчётов
    ├── console_report.py
    └── excel_report.py
```

## Пайплайн

1. **Поиск активных тендеров** — Скрейпинг rostender.info с фильтрами
2. **Извлечение заказчиков** — Получение ИНН и названий организаций
3. **Анализ истории** — Поиск завершённых тендеров по каждому заказчику
4. **Парсинг протоколов** — Извлечение количества участников из PDF/DOCX
5. **Расчёт метрик** — Определение уровня конкуренции
6. **Генерация отчёта** — Excel + консоль

## Зависимости

- **playwright** — Браузерная автоматизация
- **aiosqlite** — Асинхронный SQLite
- **openpyxl** — Генерация Excel
- **pdfplumber** — Извлечение текста из PDF
- **python-docx** — Парсинг DOCX
- **loguru** — Логирование

## Тесты

```bash
pytest tests/
```
