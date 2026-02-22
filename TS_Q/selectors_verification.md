# Верификация CSS-селекторов rostender.info

> Проверено: 20.02.2026 по реальному HTML страниц `/extsearch/advanced` и результатов поиска.

## Статус: Частично верифицировано

## Форма расширенного поиска (`/extsearch/advanced`)

Все селекторы формы **подтверждены** по реальному HTML:

| Элемент | Селектор в коде | Реальный HTML | Статус |
|---------|----------------|---------------|--------|
| Ключевые слова | `#keywords` | `<input id="keywords" name="keywords">` | OK |
| Исключения | `#exceptions` | `<input id="exceptions" name="exceptions">` | OK |
| Цена от (скрытое) | `#min_price` | `<input id="min_price" name="min_price">` | OK |
| Цена от (дисплей) | `#min_price-disp` | `<input id="min_price-disp">` (maskMoney) | OK |
| Скрывать без цены | `#hide_price` | `<input id="hide_price" type="checkbox">` | OK |
| Этап | `#states` | `<select id="states" name="states[]" multiple>` | OK |
| Способ размещения | `#placement_ways` | `<select id="placement_ways" name="placement_ways[]" multiple>` | OK |
| Дата от | `#tender-start-date-from` | `<input id="tender-start-date-from" name="dtc_from">` | OK |
| Дата до | `#tender-start-date-to` | `<input id="tender-start-date-to" name="dtc_to">` | OK |
| Кнопка поиска | `#start-search-button` | `<button id="start-search-button" type="submit">` | OK |

### Примечание по цене

Поле `#min_price-disp` использует jQuery-плагин maskMoney с настройками:
- prefix: "₽ ", thousands: " ", precision: 0
- Скрытое поле `#min_price` хранит чистое числовое значение

В коде используется JS evaluate для установки значения в оба поля — **корректный подход**.

## Страница результатов поиска

| Элемент | Селектор в коде | Реальный HTML | Статус |
|---------|----------------|---------------|--------|
| Карточка тендера | `article.tender-row` | `<article class="tender-row row" id="90147690">` | OK |
| ID тендера | атрибут `id` у `article` | `id="90147690"` | OK |
| Ссылка/заголовок | `a.tender-info__description` | `<a class="description tender-info__description tender-info__link">` | OK |
| Цена | `.starting-price__price` | `<div class="starting-price__price starting-price--price">445 000 ₽</div>` | OK |
| Пагинация (след.) | `ul.pagination > li.last > a` | `<li class="last"><a href="?page=2">Следующая</a></li>` | OK |
| Пагинация (активная) | `li.active.disabled > span` | `<li class="active disabled"><span>1</span></li>` | INFO |

## Страница тендера (карточка)

Селекторы для извлечения ИНН и имени заказчика **НЕ верифицированы** статическим HTML
(требуется Playwright для рендеринга). Нужна проверка при первом тестовом запуске.

| Элемент | Селектор в коде | Статус |
|---------|----------------|--------|
| ИНН (кнопка) | `.toggle-counterparty` (attr `inn`) | Нужен тест |
| ИНН (текст) | regex `ИНН\s*:?\s*(\d{10,12})` | Нужен тест |
| ЕИС-ссылка | `a[href*='zakupki.gov.ru']` | Нужен тест |
| Имя заказчика | regex по ООО/АО/ПАО/... | Нужен тест |

## Когда проводить проверку

1. **Шаг 2 (текущий)** — первый запуск `search_active_tenders()`: проверить карточки и пагинацию.
2. **Шаг 2 (текущий)** — первый запуск `extract_inn_from_page()`: проверить ИНН и имя заказчика.
3. **Шаг 3 (исторический поиск)** — повторная проверка, т.к. страница результатов для завершённых тендеров может иметь другую структуру.
4. **Шаг 4 (парсинг протоколов)** — проверить структуру HTML-протокола на странице тендера.

## Как проводить проверку

```python
# Быстрый тест с headless=False для визуальной проверки:
async with create_browser(headless=False) as browser:
    async with create_page(browser) as page:
        tenders = await search_active_tenders(page)
        print(f"Найдено: {len(tenders)}")
        for t in tenders[:3]:
            print(t)
```

При каждом запуске смотреть логи на:
- `"Результаты поиска не найдены"` — возможно, селекторы карточек не сработали
- `"ИНН не найден"` — селекторы ИНН не подошли
- Количество карточек (ожидается ~20 на страницу)
