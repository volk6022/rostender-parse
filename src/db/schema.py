"""DDL-схема SQLite для Rostender Parser."""

SCHEMA_SQL = """
-- Заказчики
CREATE TABLE IF NOT EXISTS customers (
    inn             TEXT PRIMARY KEY,
    name            TEXT,
    status          TEXT DEFAULT 'new',   -- new | processing | extended_processing | extended_analyzed | analyzed | error
    last_analysis_date DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Тендеры (активные + исторические)
CREATE TABLE IF NOT EXISTS tenders (
    tender_id       TEXT PRIMARY KEY,
    customer_inn    TEXT NOT NULL,
    url             TEXT,
    source_urls     TEXT,
    title           TEXT,
    price           REAL,
    publish_date    DATETIME,
    tender_status   TEXT NOT NULL,        -- active | completed
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_inn) REFERENCES customers(inn)
);

-- Результаты парсинга протоколов
CREATE TABLE IF NOT EXISTS protocol_analysis (
    id                                INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id                         TEXT NOT NULL,
    tender_protocol_index             INTEGER,           -- NULL для де-дуплицированного результата, 1+ для отдельных протоколов
    participants_count                INTEGER,            -- NULL = не удалось определить
    parse_source                      TEXT,               -- html | docx | pdf_text |eis_html | eis_docx | deduplicated
    parse_status                      TEXT NOT NULL,      -- success | failed | skipped_scan | no_protocol | deduplicated
    doc_path                          TEXT,               -- Путь к скачанному файлу (можно NULL для агрегированного результата)
    notes                             TEXT,               -- Доп. информация / причина ошибки
    analyzed_at                       DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tender_id, tender_protocol_index),            -- Один протокол только на один tender_id
    FOREIGN KEY(tender_id) REFERENCES tenders(tender_id)
);

-- Итоговые результаты: интересные активные тендеры
CREATE TABLE IF NOT EXISTS results (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    active_tender_id        TEXT NOT NULL,
    customer_inn            TEXT NOT NULL,
    total_historical        INTEGER,      -- Всего найдено завершённых
    total_analyzed          INTEGER,      -- Успешно проанализировано
    total_skipped           INTEGER,      -- Не удалось определить → игнорируются
    low_competition_count   INTEGER,      -- С участниками ≤ порог
    competition_ratio       REAL,         -- low_competition_count / total_analyzed
    is_interesting          BOOLEAN DEFAULT 0,
    source                  TEXT DEFAULT 'primary',  -- primary | extended
    created_at              DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(active_tender_id) REFERENCES tenders(tender_id),
    FOREIGN KEY(customer_inn)     REFERENCES customers(inn)
);
"""
