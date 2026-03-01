# План: Авторизация на rostender.info + конфигурация через config.yaml

## Цели

1. Добавить авторизацию на rostender.info (логин/пароль через форму на `/login`)
2. Перенести все настройки из захардкоженного `src/config.py` в внешний файл `config.yaml`
3. Рефакторинг `main.py` — один процесс браузера на весь pipeline вместо трёх

---

## Контекст

### Текущее состояние
- Все параметры захардкожены как Python-константы в `src/config.py` (90 строк)
- Нет авторизации — сайт используется анонимно
- В `main.py` браузер создаётся 3 раза (по одному на каждый этап pipeline)
- CLI-аргументы (`--keywords`, `--min-price` и т.д.) переопределяют значения из `config.py`

### Страница авторизации rostender.info/login
- Форма: POST на `/login`
- Поле логина: `input#username` (name=`username`)
- Поле пароля: `input#password` (name=`password`)
- Чекбокс «Запомнить меня»: `input#rememberme`
- CSRF-токен: скрытое поле `_csrf-frontend` (генерируется автоматически)
- Кнопка входа: `button[name="login-button"]`

### Сессия в Playwright
- Cookies привязаны к **BrowserContext**, а не к Browser и не к Page
- `create_page()` создаёт новый BrowserContext каждый раз → cookies не переносятся между вызовами
- Решение: один `create_browser()` + `create_page()` на весь pipeline, один логин в начале

---

## Файлы для изменения/создания

| Файл | Действие | Описание |
|------|----------|----------|
| `pyproject.toml` | изменить | добавить `pyyaml>=6.0` в зависимости |
| `config.yaml.example` | создать | шаблон конфигурации (коммитится в git) |
| `.gitignore` | изменить | добавить `config.yaml` |
| `src/config.py` | переписать | загрузка из YAML вместо хардкода |
| `src/scraper/auth.py` | создать | модуль авторизации на rostender.info |
| `src/main.py` | рефакторинг | один browser/page + вызов login |

### Файлы без изменений
- `src/scraper/browser.py`
- `src/scraper/active_tenders.py`
- `src/scraper/historical_search.py`
- `src/scraper/eis_fallback.py`
- `src/parser/*`
- `src/analyzer/*`
- `src/db/*`
- `src/reporter/*`
- `tests/*`

---

## Порядок выполнения

### Шаг 1. `pyproject.toml` — добавить pyyaml

Добавить одну строку в секцию `dependencies`:

```toml
"pyyaml>=6.0",
```

---

### Шаг 2. `config.yaml.example` — создать шаблон

Файл в корне проекта с дефолтными значениями и комментариями. Логин/пароль пустые.
Коммитится в git как образец для пользователя.

```yaml
# ── Авторизация на rostender.info (обязательно) ────────────────────
rostender_login: ""
rostender_password: ""

# ── Поиск активных тендеров ────────────────────────────────────────
search_keywords:
  - "Поставка"
  - "Поставки"
  - "Закупка"
  - "Снабжение"
  - "Приобретение"
  - "Оборудование и материалы"
  - "Оборудование"
  - "Станок"
  - "Станки"
  - "Лист"
  - "Труба"

exclude_keywords:
  - "Выполнение работ"
  - "Капитальный ремонт"
  - "Оказание услуг"
  - "Лекарственные препараты"
  - "Благоустройство"
  - "Предоставление субсидий"
  - "Аренда"
  - "Строительство"
  - "Отбор получателей субсидии"
  - "Возмещение"
  - "Оказание консультационных услуг"
  - "Лекарственного препарата"
  - "Выполнение строительно-монтажных работ"

# Диапазон дат публикации (формат "DD.MM.YYYY"). null — сегодня.
search_date_from: null
search_date_to: null

# ── Пороги цен (руб.) ─────────────────────────────────────────────
min_price_active: 25000000       # Мин. цена активных тендеров (Этап 1)
min_price_related: 2000000       # Мин. цена доп. тендеров заказчика (Этап 3)
min_price_historical: 1000000    # Мин. цена при поиске исторических (Этап 2)

# ── Анализ конкуренции ─────────────────────────────────────────────
historical_tenders_limit: 5      # Кол-во последних завершённых для анализа
max_participants_threshold: 2    # Макс. участников для «низкой конкуренции»
competition_ratio_threshold: 0.8 # Доля тендеров с низкой конкуренцией

# ── Хранение ──────────────────────────────────────────────────────
keep_downloaded_docs: true       # Сохранять документы после анализа
cleanup_after_days: 30           # Через сколько дней чистить старые файлы

# ── Вывод ─────────────────────────────────────────────────────────
output_formats:
  - "console"
  - "excel"
```

---

### Шаг 3. `.gitignore` — добавить config.yaml

В секцию `### Project-specific` добавить:

```
config.yaml
```

Чтобы реальный файл с паролем не попал в репозиторий.

---

### Шаг 4. `src/config.py` — переписать

#### Что остаётся в Python (не в YAML):
- Вычисляемые пути: `PROJECT_ROOT`, `DATA_DIR`, `DOWNLOADS_DIR`, `REPORTS_DIR`, `DB_PATH`
- CSS-селекторы `SELECTORS` — техническая деталь, не пользовательская настройка
- Логика загрузки и валидации конфига

#### Что загружается из YAML:
- Все пользовательские параметры (ключевые слова, пороги цен, лимиты и т.д.)
- Логин и пароль

#### Новые экспортируемые константы:
- `ROSTENDER_LOGIN: str`
- `ROSTENDER_PASSWORD: str`

#### Новые CSS-селекторы (добавляются в `SELECTORS`):
```python
"login_username": "#username",
"login_password": "#password",
"login_button": "button[name='login-button']",
"logged_in_marker": ".header--notLogged",
```

#### Поведение:
- Если `config.yaml` не найден → ошибка с инструкцией `cp config.yaml.example config.yaml`
- Если `rostender_login` или `rostender_password` пустые → ошибка при старте
- Имена экспортируемых констант не меняются → остальной код (`main.py`, скрейперы) работает без изменений

---

### Шаг 5. `src/scraper/auth.py` — создать модуль авторизации

```python
async def login(page: Page) -> None:
```

Логика:
1. Переход на `{BASE_URL}/login`
2. Вежливая пауза (`polite_wait`)
3. Заполнение `#username` и `#password` из конфига
4. Клик по `button[name='login-button']`
5. Ожидание `networkidle`
6. Проверка успешности: если `.header--notLogged` всё ещё присутствует → `RuntimeError`
7. Логирование результата

---

### Шаг 6. `src/main.py` — рефакторинг

#### Суть изменений:
Вместо 3 отдельных `create_browser() / create_page()` — один на весь pipeline.

#### Было (структура):
```python
async def run():
    # ... парсинг аргументов, настройка ...

    # Этап 1
    async with create_browser() as browser:
        async with create_page(browser) as page:
            # ~45 строк

    # Этап 2
    if new_customers:
        async with create_browser() as browser:
            async with create_page(browser) as page:
                # ~150 строк

    # Этап 3
    if interesting_customers:
        async with create_browser() as browser:
            async with create_page(browser) as page:
                # ~170 строк

    # Этап 4 (отчёт, без браузера)
```

#### Станет:
```python
async def run():
    # ... парсинг аргументов, настройка ...

    async with create_browser() as browser:
        async with create_page(browser) as page:
            await login(page)

            # Этап 1: поиск активных тендеров
            # ... (логика без изменений, уменьшен indent на 2 уровня)

            # Этап 2: анализ истории
            # ... (логика без изменений)

            # Этап 3: расширенный поиск
            # ... (логика без изменений)

    # Этап 4: отчёт (вне браузера)
```

#### Конкретные правки:
1. Добавить импорт: `from src.scraper.auth import login`
2. Удалить 3 пары `async with create_browser() / create_page()` (строки 251-252, 303-304, 470-471)
3. Добавить одну пару перед Этапом 1 + `await login(page)` после неё
4. Уменьшить уровень вложенности кода этапов 1-3 (убрали 2 вложенных `async with`)
5. Этап 4 (отчёт) остаётся за пределами browser-блока

---

## Финализация

### Шаг 7. `uv lock` — обновить lockfile

```bash
uv lock
```

### Шаг 8. Запустить тесты

```bash
pytest
```

Тесты не зависят от `config.yaml` напрямую (используют собственные фикстуры), но нужно убедиться что импорты не сломались.

---

## Проверка работоспособности

1. Скопировать `config.yaml.example` → `config.yaml`
2. Заполнить реальные `rostender_login` и `rostender_password`
3. Запустить `rostender --dry-run` — проверить что конфиг загружается
4. Запустить полный pipeline — проверить авторизацию и работу всех этапов
