# Отчёт: необходимые исправления для Steps 1-6

> Дата: 23.02.2026  
> Статус: требует реализации

---

## Содержание

1. [Критические баги](#1-критические-баги)
2. [Step 1: Infrastructure](#2-step-1-infrastructure)
3. [Step 5: EIS Fallback](#3-step-5-eis-fallback-не-реализован)
4. [Рекомендации](#4-рекомендации)
5. [Чеклист реализации](#5-чеклист-реализации)

---

## 1. Критические баги

### 1.1 Результаты анализа не сохраняются в БД

**Файл:** `src/main.py:125-215`

**Проблема:**
После анализа исторических тендеров код НЕ вызывает:
- `calculate_metrics()` из `analyzer/competition.py`
- `repository.insert_result()` для сохранения в таблицу `results`

**Следствие:** Модуль анализа конкуренции (`analyzer/competition.py`) **не используется**, результаты не записываются в БД.

---

### 1.2 Dead Code — неиспользуемая функция

**Файл:** `src/db/repository.py:152`

```python
async def get_active_tenders(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    """Получить все активные тендеры."""
    cursor = await conn.execute(
        "SELECT * FROM tenders WHERE tender_status = 'active' ORDER BY price DESC"
    )
    return await cursor.fetchall()
```

**Проблема:** Функция определена, но не используется в `main.py`.

**Решение:** Удалить или использовать в Step 3 (расширенный поиск).

---

## 2. Step 1: Infrastructure

### 2.1 Status: ✅ ГОТОВ

| Файл | Статус |
|------|--------|
| `pyproject.toml` | ✅ Готово |
| `config.py` | ✅ Готово |
| `db/schema.py` | ✅ Готово |
| `db/repository.py` | ✅ Готово (кроме неиспользуемой функции) |

### 2.2 Требуемые изменения

**Файл:** `src/main.py`

Добавить импорты (примерно строка 22-38):

```python
from src.config import (
    DATA_DIR,
    DOWNLOADS_DIR,
    REPORTS_DIR,
    SEARCH_KEYWORDS,
    EXCLUDE_KEYWORDS,
    MIN_PRICE_ACTIVE,
    HISTORICAL_TENDERS_LIMIT,
    MAX_PARTICIPANTS_THRESHOLD,
    COMPETITION_RATIO_THRESHOLD,
    OUTPUT_FORMATS,
)
from src.db.repository import (
    get_connection,
    init_db,
    upsert_customer,
    upsert_tender,
    get_customers_by_status,
    get_tenders_by_customer,
    update_customer_status,
    insert_result,                       # <-- ДОБАВИТЬ
    get_protocol_analyses_for_customer,  # <-- ДОБАВИТЬ
)
from src.analyzer.competition import (    # <-- ДОБАВИТЬ
    calculate_metrics,                    # <-- ДОБАВИТЬ
    log_metrics,                          # <-- ДОБАВИТЬ
)
```

**Добавить логику сохранения результатов** после анализа протоколов (примерно строка 195-210):

```python
                            logger.info(
                                f"ИНН {inn}: протоколы проанализированы — "
                                f"success={success_count}, failed/skipped={failed_count}"
                            )

                            # === НОВЫЙ БЛОК: Расчёт метрик и сохранение результатов ===
                            # Получаем все анализы протоколов для данного заказчика
                            analyses = await get_protocol_analyses_for_customer(conn, inn)
                            
                            # Рассчитываем метрики конкуренции
                            metrics = calculate_metrics(analyses)
                            log_metrics(inn, metrics)

                            # Если заказчик определим — сохраняем результат для каждого активного тендера
                            if metrics.is_determinable:
                                active_tenders_for_inn = await get_tenders_by_customer(
                                    conn, inn, tender_status="active"
                                )
                                for active_tender in active_tenders_for_inn:
                                    await insert_result(
                                        conn,
                                        active_tender_id=active_tender["tender_id"],
                                        customer_inn=inn,
                                        total_historical=metrics.total_historical,
                                        total_analyzed=metrics.total_analyzed,
                                        total_skipped=metrics.total_skipped,
                                        low_competition_count=metrics.low_competition_count,
                                        competition_ratio=metrics.competition_ratio,
                                        is_interesting=metrics.is_interesting,
                                        source="primary",  # для Step 3 использовать "extended"
                                    )
                                await conn.commit()
                                logger.success(
                                    f"Результаты сохранены для INN {inn}: "
                                    f"is_interesting={metrics.is_interesting}"
                                )
                            # === КОНЕЦ НОВОГО БЛОКА ===

                            # 2.5 Обновляем статус → analyzed
                            await update_customer_status(conn, inn, "analyzed")
                            await conn.commit()
```

---

## 3. Step 5: EIS Fallback — НЕ РЕАЛИЗОВАН

### 3.1 Status: ❌ ОТСУТСТВУЕТ

| Компонент | Статус |
|-----------|--------|
| `src/scraper/eis_fallback.py` | ❌ Не существует |

**Проблема:**
- Файл `src/scraper/eis_fallback.py` не создан
- В `active_tenders.py:232` есть TODO-комментарий
- При отсутствии ИНН на rostender.info нет фоллбэка на zakupki.gov.ru

### 3.2 Требуемая реализация

**Создать файл:** `src/scraper/eis_fallback.py`

```python
"""Фоллбэк на zakupki.gov.ru (ЕИС) для извлечения ИНН и протоколов.

Используется когда:
1. На rostender.info не удалось извлечь ИНН заказчика
2. На rostender.info нет протокола — пробуем получить его с ЕИС
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.async_api import Page

from src.config import DOWNLOADS_DIR, MIN_PRICE_HISTORICAL
from src.scraper.browser import polite_wait, safe_goto

EIS_BASE_URL = "https://zakupki.gov.ru"
EIS_SEARCH_URL = f"{EIS_BASE_URL}/epz/order/extendedsearch/rss.html"


async def extract_inn_from_eis(page: Page, eis_url: str) -> str | None:
    """Извлекает ИНН заказчика со страницы ЕИС.

    Args:
        page: Playwright-страница.
        eis_url: URL тендера на zakupki.gov.ru.

    Returns:
        ИНН заказчика или None, если не найден.
    """
    logger.info("Извлечение ИНН со страницы ЕИС: {}", eis_url)

    await safe_goto(page, eis_url)
    await polite_wait()

    content = await page.content()

    # Паттерн 1: "ИНН: 1234567890" или "ИНН 1234567890"
    inn_match = re.search(r"ИНН\s*:?\s*(\d{10,12})", content)
    if inn_match:
        inn = inn_match.group(1)
        logger.debug("ИНН найден в контенте: {}", inn)
        return inn

    # Паттерн 2: в атрибутах data-* элементов
    inn_el = await page.query_selector("[data-inn], [data-Inn], [data-INN]")
    if inn_el:
        inn = (
            await inn_el.get_attribute("data-inn")
            or await inn_el.get_attribute("data-Inn")
            or await inn_el.get_attribute("data-INN")
        )
        if inn:
            logger.debug("ИНН найден в атрибуте: {}", inn)
            return inn

    # Паттерн 3: в блоке "Заказчик" / "Организатор"
    customer_block = await page.query_selector(".customerInfo, .organizerInfo, .col-xs-12")
    if customer_block:
        block_text = await customer_block.inner_text()
        inn_match = re.search(r"(\d{10,12})", block_text)
        if inn_match:
            inn = inn_match.group(1)
            logger.debug("ИНН найден в блоке заказчика: {}", inn)
            return inn

    logger.warning("ИНН не найден на странице ЕИС: {}", eis_url)
    return None


async def search_historical_tenders_on_eis(
    page: Page,
    customer_inn: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Ищет завершённые тендеры заказчика на zakupki.gov.ru.

    Args:
        page: Playwright-страница.
        customer_inn: ИНН заказчика.
        limit: Максимальное число результатов.

    Returns:
        Список словарей с данными тендеров:
        {
            "tender_id": str,
            "eis_url": str,
            "title": str,
            "price": float | None,
            "publish_date": str | None,
        }
    """
    logger.info("Поиск завершённых тендеров на ЕИС для ИНН {}", customer_inn)

    tenders: list[dict[str, Any]] = []

    # Переходим на страницу поиска
    search_url = f"{EIS_SEARCH_URL}?searchString={customer_inn}&morphology=on"
    await safe_goto(page, search_url)
    await polite_wait()

    # Ищем контейнер с результатами
    results_container = await page.query_selector(".search-results, .registryEntries")
    if not results_container:
        logger.info("Результаты поиска на ЕИС не найдены")
        return tenders

    # Парсим карточки тендеров
    tender_cards = await results_container.query_selector_all(
        ".registryEntry, .search-result-row, article"
    )

    for card in tender_cards[:limit]:
        try:
            # Ссылка на тендер
            link_el = await card.query_selector("a[href*='order/view']")
            if not link_el:
                continue

            href = await link_el.get_attribute("href")
            if not href:
                continue

            # Извлекаем ID из URL: .../view/common-info.html?id=1234567890
            tender_id_match = re.search(r"id=(\d+)", href)
            tender_id = tender_id_match.group(1) if tender_id_match else None

            # Название
            title_el = await card.query_selector(".title, .name, h3, h4")
            title = await title_el.inner_text() if title_el else "Без названия"

            # Цена
            price_el = await card.query_selector(".price, .sum, [data-price]")
            price_text = await price_el.inner_text() if price_el else None
            price = None
            if price_text:
                price_clean = re.sub(r"[^\d.]", "", price_text.replace(",", "."))
                price = float(price_clean) if price_clean else None

            # Проверяем, что цена соответствует критериям
            if price and price < MIN_PRICE_HISTORICAL:
                continue

            tenders.append({
                "tender_id": tender_id or href.split("=")[-1],
                "eis_url": f"{EIS_BASE_URL}{href}" if href.startswith("/") else href,
                "title": title.strip(),
                "price": price,
                "publish_date": None,  # Можно извлечь дополнительно
            })

        except Exception as e:
            logger.error("Ошибка при парсинге карточки тендера ЕИС: {}", e)
            continue

    logger.info("Найдено тендеров на ЕИС: {}", len(tenders))
    return tenders


async def get_protocol_link_from_eis(
    page: Page,
    tender_eis_url: str,
) -> str | None:
    """Находит ссылку на протокол тендера на странице ЕИС.

    Args:
        page: Playwright-страница.
        tender_eis_url: URL тендера на zakupki.gov.ru.

    Returns:
        URL протокола или None.
    """
    await safe_goto(page, tender_eis_url)
    await polite_wait()

    # Ищем ссылки на протоколы
    protocol_links = await page.query_selector_all(
        "a[href*='protocol'], a[data-link*='protocol'], .protocol a"
    )

    for link in protocol_links:
        href = await link.get_attribute("href")
        if href and "protocol" in href.lower():
            # Возвращаем полный URL
            if href.startswith("/"):
                return f"{EIS_BASE_URL}{href}"
            return href

    logger.debug("Протокол не найден на странице: {}", tender_eis_url)
    return None


async def download_protocol_from_eis(
    page: Page,
    protocol_url: str,
    tender_id: str,
    customer_inn: str,
) -> Path | None:
    """Скачивает файл протокола с ЕИС.

    Args:
        page: Playwright-страница.
        protocol_url: URL для скачивания протокола.
        tender_id: ID тендера.
        customer_inn: ИНН заказчика.

    Returns:
        Путь к скачанному файлу или None.
    """
    download_dir = DOWNLOADS_DIR / customer_inn / tender_id / "eis"
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with page.expect_download(timeout=60_000) as download_info:
            await page.goto(protocol_url)
            await page.wait_for_load_state("networkidle")

        download = await download_info.value
        
        # Определяем расширение из имени файла
        filename = download.suggested_filename
        file_path = download_dir / filename
        
        await download.save_as(str(file_path))
        logger.info("Скачан протокол ЕИС: {} ({} байт)", 
                    file_path.name, file_path.stat().st_size)
        return file_path

    except Exception as e:
        logger.error("Ошибка скачивания протокола с ЕИС: {}", e)
        return None


# === Функции-обёртки для интеграции ===

async def fallback_extract_inn(page: Page, tender_url: str) -> str | None:
    """Фоллбэк для извлечения ИНН через ЕИС.

    Используется когда на rostender.info ИНН не найден в атрибуте.

    Args:
        page: Playwright-страница.
        tender_url: URL тендера на rostender.info.

    Returns:
        ИНН заказчика или None.
    """
    # Переходим на страницу тендера
    await safe_goto(page, tender_url)
    await polite_wait()

    # Ищем ссылку на ЕИС
    eis_link_el = await page.query_selector("a[href*='zakupki.gov.ru']")
    if not eis_link_el:
        logger.debug("ЕИС-ссылка не найдена на странице тендера")
        return None

    eis_url = await eis_link_el.get_attribute("href")
    if not eis_url:
        return None

    # Извлекаем ИНН со страницы ЕИС
    return await extract_inn_from_eis(page, eis_url)


async def fallback_get_protocol(
    page: Page,
    tender_eis_url: str,
    tender_id: str,
    customer_inn: str,
) -> Path | None:
    """Фоллбэк для получения протокола с ЕИС.

    Используется когда на rostender.info протокол не найден.

    Args:
        page: Playwright-страница.
        tender_eis_url: URL тендера на zakupki.gov.ru.
        tender_id: ID тендера.
        customer_inn: ИНН заказчика.

    Returns:
        Путь к скачанному протоколу или None.
    """
    # Находим ссылку на протокол
    protocol_url = await get_protocol_link_from_eis(page, tender_eis_url)
    if not protocol_url:
        logger.debug("Протокол не найден на ЕИС")
        return None

    # Скачиваем протокол
    return await download_protocol_from_eis(page, protocol_url, tender_id, customer_inn)
```

### 3.3 Интеграция в main.py

**Файл:** `src/main.py`

Добавить импорт (примерно строка 37):

```python
from src.scraper.active_tenders import (
    extract_inn_from_page,
    get_customer_name,
    search_active_tenders,
)
from src.scraper.historical_search import search_historical_tenders
from src.scraper.browser import create_browser, create_page
from src.scraper.eis_fallback import fallback_extract_inn  # <-- ДОБАВИТЬ
from src.parser.html_protocol import analyze_tender_protocol
```

**Изменить логику извлечения ИНН** в main.py (примерно строка 98-110):

```python
                    # 1.2 Для каждого тендера заходим внутрь для извлечения ИНН
                    logger.info(f"Обработка тендера {t_data['tender_id']}...")
                    
                    # Пробуем сначала на rostender.info
                    inn = await extract_inn_from_page(page, t_data["url"])

                    if not inn:
                        # Фоллбэк: пробуем получить ИНН через ЕИС
                        logger.info("ИНН не найден на rostender.info, пробуем ЕИС...")
                        inn = await fallback_extract_inn(page, t_data["url"])

                    if not inn:
                        logger.warning(
                            f"Пропуск тендера {t_data['tender_id']} (ИНН не найден)"
                        )
                        continue
```

### 3.4 Интеграция в active_tenders.py (опционально)

**Файл:** `src/scraper/active_tenders.py`

Раскомментировать или обновить TODO (строка 232):

```python
    # Попробуем найти ссылку на ЕИС (zakupki.gov.ru)
    # TODO: Шаг 5 (eis_fallback.py) — реализовать переход по ссылке ЕИС
    # ДЛЯ ИЗВЛЕЧЕНИЯ ИНН И ПРОТОКОЛОВ С zakupki.gov.ru.
    # РЕАЛИЗОВАНО: используется fallback_extract_inn из main.py
```

---

## 4. Рекомендации

### 4.1 Добавить type hints для async функций

Некоторые функции в `repository.py` не имеют полных type hints:

```python
# repository.py:75
async def get_customers_by_status(
    conn: aiosqlite.Connection,
    status: str,
) -> list[aiosqlite.Row]:  # ✅ Уже есть
```

Это уже корректно.

### 4.2 Обработка ошибок в main.py

Рекомендуется добавить болееGraceful обработку ошибок:

```python
try:
    # ... существующий код ...
except Exception as exc:
    logger.error(f"Ошибка при обработке ИНН {inn}: {exc}")
    await update_customer_status(conn, inn, "error")
    await conn.commit()
    continue  # Продолжаем со следующим заказчиком
```

### 4.3 Логирование прогресса

Добавить счётчики:

```python
total_customers = len(new_customers)
for idx, customer in enumerate(new_customers, 1):
    logger.info(f"Обработка {idx}/{total_customers}: INN {inn}")
    # ...
```

---

## 5. Чеклист реализации

- [ ] **main.py:** Добавить импорты `calculate_metrics`, `log_metrics`, `insert_result`, `get_protocol_analyses_for_customer`
- [ ] **main.py:** После анализа протоколов вызвать расчёт метрик и сохранить результаты в БД
- [ ] **main.py:** Интегрировать `fallback_extract_inn` в основной поток
- [ ] **scraper/eis_fallback.py:** **Создать** новый файл с функциями фоллбэка
- [ ] **repository.py:** Опционально удалить неиспользуемую функцию `get_active_tenders`

---

## Файлы для изменения

| Файл | Изменение |
|------|-----------|
| `src/main.py` | Добавить импорты + логику сохранения результатов + интеграция EIS |
| `src/scraper/eis_fallback.py` | **Создать** (новый файл, ~250 строк) |
| `src/db/repository.py` | Опционально: удалить `get_active_tenders` |

---

## Примечание

После реализации этих изменений необходимо:
1. Протестировать scraper с реальными данными
2. Проверить логику сохранения результатов в БД
3. Убедиться, что фоллбэк на ЕИС корректно работает для тендеров без ИНН на rostender.info
