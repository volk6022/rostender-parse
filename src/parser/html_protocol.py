"""Парсинг протоколов со страниц тендеров на rostender.info.

Основной модуль этапа 4. Для каждого завершённого тендера:
1. Переходит на страницу тендера.
2. Извлекает ``tendersData`` (JSON из ``<script>``) — метаданные файлов.
3. Находит файлы протоколов (по флагу ``is_protocol`` или по заголовку).
4. Скачивает файл протокола.
5. Вызывает соответствующий парсер (HTML/TXT, DOCX, PDF).
6. Возвращает результат: количество участников, источник, статус.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger
from playwright.async_api import Page

from src.config import DOWNLOADS_DIR, KEEP_DOWNLOADED_DOCS
from src.db.repository import (
    update_tender_source_urls,
    upsert_protocol_analysis,
)
from src.parser.docx_parser import extract_participants_from_docx
from src.parser.participant_patterns import (
    ParticipantParsingResult,
    ParticipantResult,
    extract_participants_from_text,
)
from src.parser.table_analyzer import MultiProtocolAnalysis, ProtocolData
from src.parser.pdf_parser import extract_participants_from_pdf, is_scan_pdf
from src.scraper.browser import polite_wait, safe_goto
from src.scraper.eis_fallback import fallback_get_protocol
from src.scraper.gpb_fallback import (
    download_protocol_from_gpb,
    get_protocol_links_from_gpb,
)
from src.scraper.rosatom_fallback import (
    download_protocol_from_rosatom,
    get_protocol_links_from_rosatom,
)
from src.scraper.roseltorg_fallback import (
    download_protocol_from_roseltorg,
    get_protocol_links_from_roseltorg,
)
from src.scraper.source_links import (
    extract_source_urls,
    get_source_url,
    parse_source_urls,
)


@dataclass
class ProtocolFile:
    """Метаданные файла протокола из tendersData."""

    file_id: int
    tender_id: str
    title: str
    link: str
    extension: str | None
    size: int
    is_protocol: bool


@dataclass
class ProtocolParseResult:
    """Результат парсинга протокола одного тендера."""

    tender_id: str
    participants_count: int | None
    parse_source: str | None  # html | docx | pdf_text | txt
    parse_status: str  # success | failed | skipped_scan | no_protocol
    doc_path: str | None
    notes: str | None


def _extract_tenders_data(page_html: str, tender_id: str) -> dict[str, Any] | None:
    """Извлекает JSON ``tendersData`` из HTML страницы тендера.

    Структура в HTML:
    ``var tendersData = {"<tender_id>": {..., "files_by_date": {...}}};``

    Returns:
        Словарь ``files_by_date`` или None, если не найден.
    """
    # Ищем var tendersData = {...};
    match = re.search(
        r"var\s+tendersData\s*=\s*(\{.*?\})\s*;\s*(?:</script>|$)",
        page_html,
        re.DOTALL,
    )
    if not match:
        logger.debug("tendersData не найден в HTML")
        return None

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        logger.warning("Ошибка разбора JSON tendersData: {}", exc)
        return None

    # tender_id может быть строкой или числом в JSON
    tender_data = data.get(str(tender_id)) or data.get(int(tender_id))  # type: ignore[arg-type]
    if tender_data is None:
        # Если в объекте один ключ — берём его
        if len(data) == 1:
            tender_data = next(iter(data.values()))
        else:
            logger.debug("Ключ {} не найден в tendersData", tender_id)
            return None

    return tender_data


def _find_protocol_files(tender_data: dict[str, Any]) -> list[ProtocolFile]:
    """Находит файлы протоколов в ``files_by_date``.

    Приоритет:
    1. Файлы с флагом ``is_protocol: true``
    2. Файлы с заголовком, содержащим «протокол»
    """
    files_by_date: dict[str, list[dict]] = tender_data.get("files_by_date", {})
    protocols: list[ProtocolFile] = []
    non_flagged_protocols: list[ProtocolFile] = []

    # Диагностика: общее количество файлов и дат
    total_files = sum(len(files) for files in files_by_date.values())
    logger.debug(
        "files_by_date: {} дат, {} файлов всего",
        len(files_by_date),
        total_files,
    )

    for _date, files in files_by_date.items():
        for f in files:
            pf = ProtocolFile(
                file_id=f.get("id", 0),
                tender_id=str(f.get("tid", "")),
                title=f.get("title", ""),
                link=f.get("link", ""),
                extension=f.get("extension") or _guess_extension(f),
                size=f.get("size", 0),
                is_protocol=bool(f.get("is_protocol", False)),
            )

            if pf.is_protocol:
                protocols.append(pf)
            elif re.search(r"протокол", pf.title, re.IGNORECASE):
                non_flagged_protocols.append(pf)

    # Предпочитаем файлы с is_protocol=True, иначе по заголовку
    result = protocols or non_flagged_protocols

    if result:
        logger.debug(
            "Найдено файлов протоколов: {} (по флагу: {}, по заголовку: {})",
            len(result),
            len(protocols),
            len(non_flagged_protocols),
        )
    else:
        logger.debug(
            "Протоколы не найдены среди {} файлов (is_protocol=True: 0, по заголовку: 0)",
            total_files,
        )

    return result


def _guess_extension(file_info: dict) -> str | None:
    """Определяет расширение файла по полю ``fsid`` или ``ext``."""
    ext = file_info.get("ext")
    if ext:
        return ext.lower()

    fsid = file_info.get("fsid", "")
    if "." in fsid:
        return fsid.rsplit(".", 1)[-1].lower()

    return None


def _prioritize_protocols(protocols: list[ProtocolFile]) -> list[ProtocolFile]:
    """Сортирует протоколы по приоритету формата для парсинга.

    Порядок: docx > doc > htm/html > txt > pdf (текст) > остальные
    """
    priority = {"docx": 0, "doc": 1, "htm": 2, "html": 2, "txt": 3, "pdf": 4}

    return sorted(
        protocols,
        key=lambda p: priority.get(p.extension or "", 10),
    )


async def _download_protocol(
    page: Page,
    protocol: ProtocolFile,
    tender_id: str,
    customer_inn: str,
) -> Path | None:
    """Скачивает файл протокола через Playwright.

    Файлы сохраняются в ``downloads/{inn}/{tender_id}/``

    Returns:
        Путь к скачанному файлу или None при ошибке.
    """
    if not protocol.link:
        logger.warning("Нет ссылки для скачивания протокола {}", protocol.title)
        return None

    # Создаём директорию для файла
    download_dir = DOWNLOADS_DIR / customer_inn / tender_id
    download_dir.mkdir(parents=True, exist_ok=True)

    # Определяем имя файла
    ext = protocol.extension or "bin"
    safe_title = re.sub(r'[<>:"/\\|?*]', "_", protocol.title)[:100]
    filename = f"{safe_title}.{ext}"
    file_path = download_dir / filename

    # Если файл уже скачан, используем его
    if file_path.exists() and file_path.stat().st_size > 0:
        logger.debug("Файл уже скачан: {}", file_path)
        return file_path

    try:
        # Скачиваем через Playwright
        async with page.expect_download(timeout=30_000) as download_info:
            await page.evaluate(
                """(url) => {
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = '';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                }""",
                protocol.link,
            )
        download = await download_info.value
        await download.save_as(str(file_path))
        logger.debug(
            "Скачан протокол: {} ({} байт)", file_path.name, file_path.stat().st_size
        )
        return file_path

    except Exception:
        # Фоллбэк: прямой HTTP-запрос через page.goto + response
        logger.debug("expect_download не сработал, пробуем прямой запрос...")
        try:
            response = await page.request.get(protocol.link)
            if response.ok:
                body = await response.body()
                file_path.write_bytes(body)
                logger.debug(
                    "Скачан протокол (HTTP): {} ({} байт)",
                    file_path.name,
                    len(body),
                )
                return file_path
            else:
                logger.error(
                    "Ошибка скачивания {}: HTTP {}",
                    protocol.title,
                    response.status,
                )
                return None
        except Exception as exc2:
            logger.error("Ошибка скачивания протокола {}: {}", protocol.title, exc2)
            return None


def _parse_downloaded_file(file_path: Path) -> tuple[ParticipantResult, str]:
    """Парсит скачанный файл протокола. Возвращает (результат, parse_source)."""
    ext = file_path.suffix.lower().lstrip(".")

    if ext in ("htm", "html", "txt"):
        text = file_path.read_text(encoding="utf-8", errors="replace")
        # Для HTML — убираем теги
        if ext in ("htm", "html"):
            clean_text = re.sub(r"<[^>]+>", " ", text)
            clean_text = re.sub(r"\s+", " ", clean_text)
            result = extract_participants_from_text(clean_text)
            source = "html"
        else:
            result = extract_participants_from_text(text)
            source = "txt"
        return result, source

    elif ext in ("docx",):
        result = extract_participants_from_docx(file_path)
        return result, "docx"

    elif ext in ("doc",):
        # .doc (старый формат) — пробуем как текстовый файл
        # python-docx не поддерживает .doc, пробуем прочитать как текст
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            if len(text.strip()) > 50:
                result = extract_participants_from_text(text)
                return result, "doc_text"
        except Exception:
            pass
        logger.info("Файл .doc {} не поддерживается (только .docx)", file_path.name)
        return (
            ParticipantParsingResult(
                count=None, numbers=[], method="doc_unsupported", confidence="low"
            ),
            "doc",
        )

    elif ext in ("pdf",):
        if is_scan_pdf(file_path):
            return (
                ParticipantParsingResult(
                    count=None, numbers=[], method="pdf_scan_skip", confidence="low"
                ),
                "pdf_scan",
            )
        result = extract_participants_from_pdf(file_path)
        return result, "pdf_text"

    else:
        logger.warning("Неизвестное расширение протокола: .{}", ext)
        return (
            ParticipantParsingResult(
                count=None, numbers=[], method=f"unknown_ext_{ext}", confidence="low"
            ),
            f"unknown_{ext}",
        )


async def _try_external_fallbacks(
    page: Page,
    source_urls_str: str,
    tender_id: str,
    customer_inn: str,
    conn: aiosqlite.Connection,
) -> ProtocolParseResult | None:
    """Пробует получить протоколы с внешних площадок (EIS, GPB, Rosatom, Roseltorg)."""
    sources = parse_source_urls(source_urls_str)

    # Приоритет аналогичен unified_fallback
    priority = ["eis", "gpb", "rosatom", "roseltorg"]

    for platform in priority:
        if platform not in sources:
            continue

        url = sources[platform]
        logger.info(f"Пробуем фоллбэк протоколов {platform}: {url}")

        try:
            protocol_path = None
            if platform == "eis":
                protocol_path = await fallback_get_protocol(
                    page=page,
                    tender_eis_url=url,
                    tender_id=tender_id,
                    customer_inn=customer_inn,
                )
            elif platform == "gpb":
                links = await get_protocol_links_from_gpb(page, url)
                if links:
                    protocol_path = await download_protocol_from_gpb(
                        page, links[0], tender_id, customer_inn
                    )
            elif platform == "rosatom":
                links = await get_protocol_links_from_rosatom(page, url)
                if links:
                    protocol_path = await download_protocol_from_rosatom(
                        page, links[0], tender_id, customer_inn
                    )
            # elif platform == "roseltorg":
            #     links = await get_protocol_links_from_roseltorg(page, url)
            #     if links:
            #         protocol_path = await download_protocol_from_roseltorg(
            #             page, links[0], tender_id, customer_inn
            #         )

            if protocol_path:
                # Парсим скачанный протокол
                participant_result, parse_source = _parse_downloaded_file(protocol_path)

                if participant_result.count is not None:
                    doc_path = (
                        str(protocol_path.relative_to(DOWNLOADS_DIR))
                        if KEEP_DOWNLOADED_DOCS
                        else None
                    )
                    result = ProtocolParseResult(
                        tender_id=tender_id,
                        participants_count=participant_result.count,
                        parse_source=f"{platform}_{parse_source}",
                        parse_status="success",
                        doc_path=doc_path,
                        notes=f"{platform.upper()}: method={participant_result.method}, confidence={participant_result.confidence}",
                    )
                    await _save_result(conn, result)
                    logger.success(
                        "Тендер {} ({}): {} участников (источник: {}_{})",
                        tender_id,
                        platform.upper(),
                        participant_result.count,
                        platform,
                        parse_source,
                    )
                    return result

        except Exception as e:
            logger.error(f"Ошибка фоллбэка протоколов {platform}: {e}")

    return None


async def analyze_tender_protocol(
    page: Page,
    tender_id: str,
    tender_url: str,
    customer_inn: str,
    conn: aiosqlite.Connection,
) -> ProtocolParseResult:
    """Полный цикл анализа протокола одного завершённого тендера.

    1. Переходит на страницу тендера
    2. Извлекает tendersData из JS
    3. Находит файлы протоколов
    4. Скачивает лучший протокол
    5. Парсит для извлечения числа участников
    6. Сохраняет результат в БД

    Args:
        page: Playwright-страница.
        tender_id: ID тендера.
        tender_url: URL тендера на rostender.info.
        customer_inn: ИНН заказчика.
        conn: Соединение с БД.

    Returns:
        ProtocolParseResult с результатами.
    """
    logger.info("Анализ протокола тендера {} (ИНН {})", tender_id, customer_inn)

    # ── 1. Переход на страницу тендера ────────────────────────────────────
    await safe_goto(page, tender_url)
    await polite_wait()

    # Извлекаем и сохраняем ссылки на источники (всегда, для всех тендеров)
    source_urls = await extract_source_urls(page)
    if source_urls:
        await update_tender_source_urls(conn, tender_id, source_urls)
        await conn.commit()

    # ── Диагностика: определяем текущий этап тендера на странице ────────
    try:
        stage_text = await page.evaluate("""
            () => {
                // Ищем бейдж/метку этапа на странице тендера
                const badge = document.querySelector('.tender-state, .state-badge, .stage-label, .tender-status');
                if (badge) return badge.innerText.trim();
                // Альтернатива: ищем текст «Этап:» в боковой панели
                const allText = document.body.innerText;
                const m = allText.match(/(?:Этап|Стадия|Статус)[:\\s]+([^\\n]{3,40})/i);
                return m ? m[1].trim() : null;
            }
        """)
        if stage_text:
            logger.debug("Тендер {} — этап на странице: «{}»", tender_id, stage_text)
    except Exception:
        pass  # Не критично — чисто диагностика

    # ── 2. Извлечение tendersData ────────────────────────────────────────
    page_html = await page.content()
    tender_data = _extract_tenders_data(page_html, tender_id)

    if tender_data is None:
        # Пробуем внешние фоллбэки
        if source_urls:
            logger.info("tendersData не найден, пробуем внешние площадки...")
            result = await _try_external_fallbacks(
                page, source_urls, tender_id, customer_inn, conn
            )
            if result:
                return result

        result = ProtocolParseResult(
            tender_id=tender_id,
            participants_count=None,
            parse_source=None,
            parse_status="no_protocol",
            doc_path=None,
            notes="tendersData не найден в HTML страницы",
        )
        await _save_result(conn, result)
        return result

    # ── 3. Поиск файлов протоколов ───────────────────────────────────────
    protocols = _find_protocol_files(tender_data)

    if not protocols:
        # Пробуем внешние фоллбэки
        if source_urls:
            logger.info(
                "Протоколы не найдены на rostender.info, пробуем внешние площадки..."
            )
            result = await _try_external_fallbacks(
                page, source_urls, tender_id, customer_inn, conn
            )
            if result:
                return result

        result = ProtocolParseResult(
            tender_id=tender_id,
            participants_count=None,
            parse_source=None,
            parse_status="no_protocol",
            doc_path=None,
            notes="Файлы протоколов не найдены в tendersData",
        )
        await _save_result(conn, result)
        return result

    # Сортируем по приоритету формата
    sorted_protocols = _prioritize_protocols(protocols)
    logger.debug(
        "Тендер {}: {} протоколов, форматы: {}",
        tender_id,
        len(sorted_protocols),
        [p.extension for p in sorted_protocols],
    )

    # ── 4. Скачивание и парсинг всех протоколов (с дедупликацией) ───────────
    multi_analysis = MultiProtocolAnalysis(tender_id=tender_id)
    protocol_index = 0
    scan_found = False
    last_doc_path: str | None = None
    last_parse_source: str | None = None

    for protocol in sorted_protocols:
        logger.debug(
            "Пробуем протокол: '{}' (.{})",
            protocol.title[:60],
            protocol.extension,
        )

        # Скачиваем
        file_path = await _download_protocol(page, protocol, tender_id, customer_inn)
        if file_path is None:
            continue

        # Парсим
        participant_result, parse_source = _parse_downloaded_file(file_path)

        # Если PDF-скан — пропускаем к следующему файлу
        if participant_result.method == "pdf_scan_skip":
            logger.info("Протокол {} — PDF-скан, пробуем следующий", protocol.title)
            scan_found = True
            continue

        # Определяем doc_path для хранения
        doc_path = (
            str(file_path.relative_to(DOWNLOADS_DIR)) if KEEP_DOWNLOADED_DOCS else None
        )

        protocol_index += 1

        # Добавляем данные протокола в MultiProtocolAnalysis
        protocol_data = ProtocolData(
            protocol_index=protocol_index,
            file_path=doc_path,
            parse_source=parse_source,
            application_numbers=participant_result.numbers,
            raw_count=participant_result.count,
            parse_method=participant_result.method,
            confidence=participant_result.confidence,
        )
        multi_analysis.add_protocol(protocol_data)

        if participant_result.count is not None:
            last_doc_path = doc_path
            last_parse_source = parse_source
            logger.debug(
                "Протокол '{}' (.{}): {} участников (метод: {}, заявки: {})",
                protocol.title[:50],
                protocol.extension,
                participant_result.count,
                participant_result.method,
                participant_result.numbers,
            )
        else:
            logger.debug(
                "Протокол '{}' (.{}): участники не определены ({})",
                protocol.title[:50],
                protocol.extension,
                participant_result.method,
            )

    # ── 5. Агрегация результатов ──────────────────────────────────────────
    final_count = multi_analysis.get_final_count()

    if final_count is not None:
        # Определяем лучший источник для записи
        best_protocol = next(
            (p for p in multi_analysis.protocols if p.raw_count is not None),
            multi_analysis.protocols[0] if multi_analysis.protocols else None,
        )

        if multi_analysis.has_deduplication():
            # Было несколько протоколов с дедупликацией
            notes = (
                f"deduplicated: {multi_analysis.summary_notes()}, "
                f"confidence={multi_analysis.get_best_confidence()}"
            )
            effective_source = "deduplicated"
        else:
            notes = (
                f"method={best_protocol.parse_method if best_protocol else 'unknown'}, "
                f"confidence={multi_analysis.get_best_confidence()}"
            )
            effective_source = last_parse_source or "unknown"

        result = ProtocolParseResult(
            tender_id=tender_id,
            participants_count=final_count,
            parse_source=effective_source,
            parse_status="success",
            doc_path=last_doc_path,
            notes=notes,
        )
        await _save_result(conn, result)
        logger.success(
            "Тендер {}: {} участников (источник: {}, протоколов: {})",
            tender_id,
            final_count,
            effective_source,
            len(multi_analysis.protocols),
        )
        return result

    # ── 6. Ни один протокол не дал результат ─────────────────────────────
    if scan_found and len(sorted_protocols) == 1:
        parse_status = "skipped_scan"
        notes = "Единственный протокол — PDF-скан (OCR не поддерживается)"
    else:
        parse_status = "failed"
        notes = f"Не удалось извлечь участников из {len(sorted_protocols)} протокол(ов)"

    result = ProtocolParseResult(
        tender_id=tender_id,
        participants_count=None,
        parse_source=None,
        parse_status=parse_status,
        doc_path=None,
        notes=notes,
    )
    await _save_result(conn, result)
    return result


async def _save_result(
    conn: aiosqlite.Connection,
    result: ProtocolParseResult,
) -> None:
    """Сохраняет результат парсинга в таблицу protocol_analysis."""
    await upsert_protocol_analysis(
        conn,
        tender_id=result.tender_id,
        participants_count=result.participants_count,
        parse_source=result.parse_source,
        parse_status=result.parse_status,
        doc_path=result.doc_path,
        notes=result.notes,
    )
    await conn.commit()
