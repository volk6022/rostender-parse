"""Модуль для поиска активных тендеров на rostender.info."""

import asyncio
import re
from datetime import datetime
from typing import Any

from loguru import logger
from playwright.async_api import Page

from src.config import (
    EXCLUDE_KEYWORDS,
    MIN_PRICE_ACTIVE,
    MIN_PRICE_RELATED,
    SELECTORS,
)
from src.scraper.source_links import extract_source_urls
from src.scraper.common import submit_search
from src.scraper.browser import BASE_URL, polite_wait, safe_goto

# Короткий алиас для читаемости.
S = SELECTORS


# ── Внутренние хелперы (DRY) ─────────────────────────────────────────────────


async def _navigate_to_search(page: Page) -> None:
    """Перейти на главную → расширенный поиск (установить сессию + куки)."""
    await safe_goto(page, BASE_URL)
    await polite_wait()
    await safe_goto(page, f"{BASE_URL}/extsearch/advanced")
    await polite_wait()
    try:
        await page.wait_for_selector(
            "#states_chosen, #states + .chosen-container", timeout=10_000
        )
        logger.debug("Chosen-плагин инициализирован")
    except Exception:
        logger.debug("Chosen-контейнер не найден за 10 с, продолжаем...")


async def _fill_common_filters(
    page: Page,
    keywords: list[str],
    min_price: int,
) -> None:
    """Заполнить общие фильтры формы расширенного поиска.

    Включает: ключевые слова, исключения, мин. цену, скрытие без цены,
    этап «Прием заявок», исключение аукционов и ед. поставщика.
    """
    # Ключевые слова
    await page.fill(S["search_keywords_input"], ", ".join(keywords))
    # Маленькая пауза, чтобы input event обработался
    await page.wait_for_timeout(300)

    # Исключения
    await page.fill(S["search_exceptions_input"], ", ".join(EXCLUDE_KEYWORDS))
    await page.wait_for_timeout(300)

    # Цена от: используем скрытое поле напрямую через JS,
    # т.к. disp-поле имеет maskMoney-плагин, который может мешать вводу.
    await page.evaluate(
        """
        ([val, selPrice, selDisp]) => {
            document.querySelector(selPrice).value = val;
            const disp = document.querySelector(selDisp);
            if (disp && typeof jQuery !== 'undefined' && jQuery(disp).maskMoney) {
                jQuery(disp).maskMoney('mask', parseFloat(val));
            } else {
                disp.value = val;
            }
        }
    """,
        [str(min_price), S["search_min_price"], S["search_min_price_disp"]],
    )

    # Скрывать без цены (checkbox visually hidden, use JS)
    await page.evaluate(
        "sel => { const el = document.querySelector(sel); if (el && !el.checked) el.click(); }",
        S["search_hide_price"],
    )

    # Этап: Прием заявок (значение "10").
    # Используем jQuery + Chosen plugin.
    await page.evaluate(
        """
        ([val, sel]) => {
            const select = document.querySelector(sel);
            Array.from(select.options).forEach(opt => opt.selected = (opt.value == val));
            $(select).trigger('chosen:updated');
            $(select).trigger('change');
        }
    """,
        ["10", S["search_states"]],
    )

    # Способ размещения: исключить Аукционы (1) и Ед. поставщик (28)
    await page.evaluate(
        """
        ([exclude_vals, sel]) => {
            const select = document.querySelector(sel);
            Array.from(select.options).forEach(opt => {
                if (exclude_vals.includes(opt.value)) {
                    opt.selected = false;
                } else {
                    opt.selected = true;
                }
            });
            $(select).trigger('chosen:updated');
            $(select).trigger('change');
        }
    """,
        [["1", "28"], S["search_placement_ways"]],
    )


async def _submit_and_collect(
    page: Page,
    *,
    log_context: str = "",
    empty_warning: str = "Результаты поиска не найдены",
) -> list[dict[str, Any]]:
    """Нажать «Искать» и собрать результаты со всех страниц пагинации.

    Args:
        page: Playwright-страница с заполненной формой.
        log_context: Контекст для лог-сообщений (напр. ``"для ИНН 123"``).
        empty_warning: Сообщение, если на первой странице нет результатов.
    """
    await submit_search(page, log_context)

    all_tenders: list[dict[str, Any]] = []

    page_num = 1

    while True:
        logger.info("Парсинг страницы #{} {}...", page_num, log_context)

        page_tenders = await parse_tenders_on_page(page)
        if not page_tenders:
            if page_num == 1:
                logger.warning(empty_warning) if not log_context else logger.info(
                    empty_warning
                )
            break

        all_tenders.extend(page_tenders)
        logger.info(
            "Страница {}: найдено {} тендеров (всего: {})",
            page_num,
            len(page_tenders),
            len(all_tenders),
        )

        # Проверка на наличие следующей страницы
        next_btn = None
        for attempt in range(2):
            try:
                next_btn = await page.query_selector(S["pagination_next"])
                break
            except Exception as e:
                if "Execution context was destroyed" in str(e) and attempt == 0:
                    logger.warning(
                        "Контекст уничтожен при поиске кнопки пагинации, повтор..."
                    )
                    await asyncio.sleep(1)
                    continue
                raise

        if not next_btn:
            logger.debug("Следующей страницы нет — пагинация завершена")
            break

        await next_btn.click()
        await page.wait_for_load_state("load")
        await polite_wait()
        page_num += 1

    return all_tenders


# ── Парсинг карточек ─────────────────────────────────────────────────────────


async def parse_tenders_on_page(
    page: Page,
    *,
    tender_status: str = "active",
) -> list[dict[str, Any]]:
    """
    Парсит карточки тендеров на текущей странице результатов.

    Извлекает все данные **одним вызовом** ``page.evaluate()`` — это
    устраняет race-condition с ``forceReload()`` (сайт перезагружает
    страницу при первом визите за день через ``localStorage``-хеш).
    При множественных ElementHandle round-trip'ах хендлы становились
    stale после reload → «Execution context was destroyed».

    Args:
        page: Playwright-страница с результатами поиска.
        tender_status: Статус для записи в результат (``"active"`` / ``"completed"``).

    Реальная структура HTML (верифицировано 19.02.2026)::

      <article class="tender-row row" id="90147690">
        <a class="description tender-info__description tender-info__link"
           href="/region/.../90147690-tender-...">Заголовок</a>
        <div class="starting-price__price starting-price--price">445 000 ₽</div>
      </article>
    """
    # ── Атомарное извлечение данных из DOM (один JS-вызов) ──────────────
    raw_items: list[dict[str, Any]] = []
    # Повтор при «Execution context was destroyed» (бывает из-за forceReload на сайте).
    for attempt in range(2):
        try:
            raw_items = await page.evaluate(
                """
                (sel) => {
                    const rows = document.querySelectorAll(sel.card);
                    return Array.from(rows).map(row => {
                        const id = row.getAttribute('id');
                        const linkEl = row.querySelector(sel.link)
                                    || row.querySelector(sel.linkAlt);
                        const priceEl = row.querySelector(sel.price);
                        return {
                            tender_id: id || null,
                            title: linkEl ? linkEl.innerText.trim() : null,
                            url: linkEl ? linkEl.getAttribute('href') : null,
                            price_text: priceEl ? priceEl.innerText : '0',
                        };
                    });
                }
                """,
                {
                    "card": S["tender_card"],
                    "link": S["tender_link"],
                    "linkAlt": S["tender_link_alt"],
                    "price": S["tender_price"],
                },
            )
            break
        except Exception as e:
            if "Execution context was destroyed" in str(e) and attempt == 0:
                logger.warning(
                    "Контекст уничтожен при парсинге страницы, повтор через 1с..."
                )
                await asyncio.sleep(1)
                continue
            logger.error(f"Ошибка при извлечении карточек через JS: {e}")
            return []

    if not raw_items:
        return []

    logger.debug(f"Карточек на странице: {len(raw_items)}")

    # ── Постобработка в Python (URL-префикс, парсинг цены) ─────────────
    tenders: list[dict[str, Any]] = []

    for item in raw_items:
        try:
            tender_id = item.get("tender_id")
            title = item.get("title")
            if not tender_id or not title:
                continue

            url = item.get("url") or ""
            if url and not url.startswith("http"):
                url = f"{BASE_URL}{url}"

            price_text: str = item.get("price_text") or "0"
            # Убираем всё кроме цифр и точки: "445 000 ₽" -> "445000"
            price = float(re.sub(r"[^\d.]", "", price_text.replace(",", ".")) or 0)

            tenders.append(
                {
                    "tender_id": tender_id,
                    "title": title,
                    "url": url,
                    "price": price,
                    "status": tender_status,
                }
            )
        except Exception as e:
            logger.error(f"Ошибка при парсинге карточки тендера: {e}")

    return tenders


# ── Публичные функции поиска ─────────────────────────────────────────────────


async def search_active_tenders(
    page: Page,
    *,
    keywords: list[str] | None = None,
    min_price: int = MIN_PRICE_ACTIVE,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """
    Выполняет поиск активных тендеров по фильтрам из ТЗ.
    Обходит все страницы пагинации.
    Возвращает список словарей с данными тендеров.

    Args:
        page: Playwright страница.
        keywords: Список ключевых слов для поиска.
        min_price: Минимальная цена.
        date_from: Дата начала поиска (DD.MM.YYYY).
        date_to: Дата окончания поиска (DD.MM.YYYY).
    """
    from src.config import SEARCH_KEYWORDS

    logger.info("Поиск активных тендеров на rostender.info...")

    effective_keywords = keywords if keywords is not None else SEARCH_KEYWORDS

    await _navigate_to_search(page)
    await _fill_common_filters(page, effective_keywords, min_price)

    # Дата публикации: из параметров или "сегодня"
    effective_date_from = date_from or datetime.now().strftime("%d.%m.%Y")
    effective_date_to = date_to or datetime.now().strftime("%d.%m.%Y")

    # Используем JS для установки дат и триггера события change,
    # чтобы обойти возможные маски ввода или datepicker'ы.
    await page.evaluate(
        """
        ([dFrom, dTo, selFrom, selTo]) => {
            const elFrom = document.querySelector(selFrom);
            const elTo = document.querySelector(selTo);
            if (elFrom) {
                elFrom.value = dFrom;
                elFrom.dispatchEvent(new Event('change', { bubbles: true }));
            }
            if (elTo) {
                elTo.value = dTo;
                elTo.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    """,
        [
            effective_date_from,
            effective_date_to,
            S["search_date_from"],
            S["search_date_to"],
        ],
    )
    logger.info("Фильтр дат: {} — {}", effective_date_from, effective_date_to)

    all_tenders = await _submit_and_collect(
        page,
        empty_warning="Результаты поиска не найдены",
    )

    logger.info(f"Итого найдено активных тендеров: {len(all_tenders)}")
    return all_tenders


async def extract_inn_from_page(
    page: Page, tender_url: str
) -> tuple[str | None, str | None]:
    """
    Переходит на страницу тендера и пытается извлечь ИНН заказчика и внешние ссылки.
    Возвращает (inn, source_urls).
    """
    await safe_goto(page, tender_url)
    await polite_wait()

    for attempt in range(2):
        try:
            source_urls = await extract_source_urls(page)

            # Поиск ИНН в атрибуте 'inn' кнопки
            btn = await page.query_selector(S["inn_button"])
            if btn:
                inn = await btn.get_attribute("inn")
                if inn and inn.strip():
                    return inn.strip(), source_urls

            # Если в атрибуте нет, ищем в тексте страницы (ИНН: 1234567890)
            content = await page.content()
            inn_match = re.search(r"ИНН\s*:?\s*(\d{10,12})", content)
            if inn_match:
                return inn_match.group(1), source_urls

            logger.warning(f"ИНН не найден для тендера: {tender_url}")
            return None, source_urls

        except Exception as e:
            if "Execution context was destroyed" in str(e) and attempt == 0:
                logger.warning(
                    "Контекст уничтожен на странице тендера, повтор через 1с..."
                )
                await asyncio.sleep(1)
                continue
            logger.error(f"Ошибка при извлечении данных со страницы тендера: {e}")
            return None, None

    return None, None


async def get_customer_name(page: Page) -> str | None:
    """
    Извлекает название организации со страницы тендера.
    Вызывать после перехода на страницу тендера (extract_inn_from_page).
    """
    content = await page.content()

    # Ищем типичные формы названий организаций в кавычках
    name_match = re.search(
        r'(?:ООО|OAO.АО|пAO|ЗАО|MКУ|MБУ|ГБУ|ФГУП|ФГБУ|MУП|ГУП|ГБУЗ|BУ)\s+"[^"]+"',
        content,
    )
    if name_match:
        return name_match.group(0)

    # Альтернативный поиск: блок с заголовком "Организатор" или "Заказчик"
    name_match = re.search(
        r"(?:Организатор|Заказчик)[^<]*?<[^>]*>([^<]{5,100})</[^>]*>",
        content,
    )
    if name_match:
        return name_match.group(1).strip()

    return None


async def search_tenders_by_inn(
    page: Page,
    inn: str,
    *,
    keywords: list[str] | None = None,
    min_price: int = MIN_PRICE_RELATED,
) -> list[dict[str, Any]]:
    """
    Поиск активных тендеров конкретного заказчика по ИНН.

    Args:
        page: Playwright-страница.
        inn: ИНН заказчика.
        keywords: Список ключевых слов для поиска.
        min_price: Минимальная цена (по умолчанию 2M для расширенного поиска).

    Returns:
        Список словарей с данными тендеров.
    """
    from src.config import SEARCH_KEYWORDS

    logger.info(f"Поиск активных тендеров для ИНН {inn} (мин. цена: {min_price})...")

    effective_keywords = keywords if keywords is not None else SEARCH_KEYWORDS

    await _navigate_to_search(page)

    # ИНН заказчика (специфичное поле, только для этого варианта поиска)
    await page.fill(S["search_customers_input"], inn)
    await page.keyboard.press("Enter")
    # Сразу закрываем подсказки
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)

    await _fill_common_filters(page, effective_keywords, min_price)

    all_tenders = await _submit_and_collect(
        page,
        log_context=f"для ИНН {inn}",
        empty_warning=f"Тендеры для ИНН {inn} не найдены",
    )

    logger.info(f"Для ИНН {inn} найдено тендеров: {len(all_tenders)}")
    return all_tenders
