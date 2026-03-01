# Rostender Parser — Project Structure

## Overview

Rostender Parser — это CLI-инструмент для автоматического поиска и анализа государственных тендеров на портале rostender.info. Система находит активные тендеры, анализирует историю заказчиков и выявляет тендеры с низкой конкуренцией.

## Architecture

```mermaid
flowchart TB
    subgraph CLI["main.py — CLI Entry Point"]
        direction TB
        run["run() async"]
    end

    subgraph Config["config.py — Configuration"]
        dirs["Paths (DATA_DIR, DOWNLOADS_DIR, REPORTS_DIR)"]
        params["Search Parameters (KEYWORDS, MIN_PRICE, etc.)"]
        selectors["CSS Selectors for rostender.info"]
    end

    subgraph Scraper["scraper/ — Web Scraping"]
        browser["browser.py<br/>Browser & Page management"]
        active["active_tenders.py<br/>Search active tenders"]
        historical["historical_search.py<br/>Search completed tenders"]
        eis["eis_fallback.py<br/>Fallback to zakupki.gov.ru"]
    end

    subgraph Parser["parser/ — Document Parsing"]
        html_proto["html_protocol.py<br/>Protocol extraction & download"]
        pdf["pdf_parser.py<br/>PDF text extraction"]
        docx["docx_parser.py<br/>DOCX parsing"]
        patterns["participant_patterns.py<br/>Regex patterns for participants"]
    end

    subgraph Analyzer["analyzer/ — Competition Analysis"]
        competition["competition.py<br/>Calculate competition metrics"]
    end

    subgraph DB["db/ — Database Layer"]
        schema["schema.py<br/>SQLite DDL"]
        repo["repository.py<br/>Async CRUD operations"]
    end

    subgraph Reporter["reporter/ — Report Generation"]
        console["console_report.py<br/>Console output"]
        excel["excel_report.py<br/>Excel .xlsx export"]
    end

    CLI --> Config
    CLI --> Scraper
    CLI --> Parser
    CLI --> Analyzer
    CLI --> DB
    CLI --> Reporter

    Scraper --> Parser
    Parser --> DB
    Analyzer --> DB
    DB --> Reporter
```

## Processing Pipeline

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant rostender as rostender.info
    participant eis as zakupki.gov.ru
    participant DB
    participant Reporter

    User->>Browser: 1. Search active tenders
    Browser->>rostender: Fill search filters
    rostender-->>Browser: Tender list
    Browser->>DB: Save tenders + customers

    loop For each customer (INN)
        Browser->>rostender: 2. Search historical tenders
        rostender-->>Browser: Completed tenders
        Browser->>DB: Save historical tenders

        loop For each historical tender
            Browser->>rostender: 3. Get protocol
            rostender-->>Browser: Protocol files
            
            alt No protocol on rostender
                Browser->>eis: Fallback to EIS
                eis-->>Browser: Protocol from EIS
            end
            
            Browser->>Browser: Parse protocol<br/>(PDF/DOCX/TXT)
            Browser->>DB: Save participant count
        end
        
        Browser->>Browser: 4. Calculate competition metrics
        DB->>Reporter: 5. Generate report
    end

    Reporter-->>User: Console + Excel output
```

## Module Details

### `config.py` — Configuration

| Component | Description |
|-----------|-------------|
| **Paths** | `DATA_DIR`, `DOWNLOADS_DIR`, `REPORTS_DIR`, `DB_PATH` |
| **Search Keywords** | `SEARCH_KEYWORDS` — words for tender search |
| **Exclude Keywords** | `EXCLUDE_KEYWORDS` — words to exclude |
| **Price Limits** | `MIN_PRICE_ACTIVE` (25M), `MIN_PRICE_RELATED` (2M), `MIN_PRICE_HISTORICAL` (1M) |
| **Analysis Thresholds** | `MAX_PARTICIPANTS_THRESHOLD` (2), `COMPETITION_RATIO_THRESHOLD` (0.8) |
| **Selectors** | CSS selectors for rostender.info page elements |

### `scraper/` — Web Scraping

#### `browser.py`

```mermaid
classDiagram
    class BrowserManager {
        +create_browser() async contextmanager
        +create_page() async contextmanager
        +safe_goto(page, url) async
        +polite_wait() async
    }
    BrowserManager --> Page
```

**Functions:**
- `create_browser(headless=True)` — Launch Chromium via Playwright
- `create_page(browser)` — Create page with configured context (UA, viewport, locale)
- `safe_goto(page, url)` — Navigate with DOM wait
- `polite_wait()` — 2-second delay between requests

#### `active_tenders.py`

**Functions:**
- `search_active_tenders(page)` — Search active tenders with filters (keywords, price, date)
- `parse_tenders_on_page(page, tender_status)` — Parse tender cards from search results
- `extract_inn_from_page(page, tender_url)` — Extract customer INN from tender page
- `get_customer_name(page)` — Extract organization name
- `search_tenders_by_inn(page, inn, min_price)` — Find tenders by customer INN

#### `historical_search.py`

**Functions:**
- `search_historical_tenders(page, customer_inn, limit, custom_keywords)` — Search completed tenders
- `extract_keywords_from_title(title)` — Extract keywords from tender title for focused search

#### `eis_fallback.py`

**Functions:**
- `fallback_extract_inn(page, tender_url)` — Extract INN via zakupki.gov.ru
- `extract_inn_from_eis(page, eis_url)` — Parse INN from EIS page
- `search_historical_tenders_on_eis(page, customer_inn, limit)` — Search tenders on EIS
- `get_protocol_link_from_eis(page, tender_eis_url)` — Find protocol link on EIS
- `download_protocol_from_eis(page, protocol_url, tender_id, customer_inn)` — Download protocol file

### `parser/` — Document Parsing

#### `html_protocol.py`

```mermaid
classDiagram
    class ProtocolFile {
        +file_id: int
        +tender_id: str
        +title: str
        +link: str
        +extension: str | None
        +size: int
        +is_protocol: bool
    }

    class ProtocolParseResult {
        +tender_id: str
        +participants_count: int | None
        +parse_source: str
        +parse_status: str
        +doc_path: str | None
        +notes: str | None
    }

    class HtmlProtocolParser {
        +analyze_tender_protocol(page, tender_id, tender_url, customer_inn, conn) async
        -_extract_tenders_data(page_html, tender_id)
        -_find_protocol_files(tender_data)
        -_download_protocol(page, protocol, tender_id, customer_inn)
        -_parse_downloaded_file(file_path)
    }

    HtmlProtocolParser --> ProtocolFile
    HtmlProtocolParser --> ProtocolParseResult
```

**Functions:**
- `analyze_tender_protocol(page, tender_id, tender_url, customer_inn, conn)` — Main protocol analysis pipeline
- `_extract_tenders_data(page_html, tender_id)` — Extract `tendersData` JSON from JS
- `_find_protocol_files(tender_data)` — Find protocol files in tender data
- `_download_protocol(page, protocol, tender_id, customer_inn)` — Download protocol file
- `_parse_downloaded_file(file_path)` — Route to appropriate parser by extension

#### `pdf_parser.py`

**Functions:**
- `is_scan_pdf(file_path)` — Check if PDF is a scan (no text layer)
- `extract_participants_from_pdf(file_path)` — Extract participants from text PDF

#### `docx_parser.py`

**Functions:**
- `extract_participants_from_docx(file_path)` — Extract participants from DOCX
- `_analyze_tables(doc)` — Analyze tables for participant rows

#### `participant_patterns.py`

```mermaid
classDiagram
    class ParticipantResult {
        +count: int | None
        +method: str
        +confidence: str
    }

    class Patterns {
        +_DIRECT_COUNT_PATTERNS
        +_NUMBERED_APPLICATION_PATTERN
        +_NUMBERED_ROWS_PATTERN
        +_INN_IN_TABLE_PATTERN
        +_SINGLE_PARTICIPANT_PATTERN
        +_ZERO_APPLICATIONS_PATTERN
        +_VOID_TENDER_PATTERN
    }

    Patterns ..> ParticipantResult
```

**Regex Patterns (priority order):**
1. Direct count: "Количество заявок: 3", "Подано 3 заявки"
2. Zero applications: "заявок не поступило", "ни одной заявки"
3. Single participant: "единственная заявка"
4. Numbered applications: "Заявка №3"
5. Numbered organization rows: "1. ООО «Рога и копыта»"
6. Unique INN count
7. Void tender: "признан несостоявшимся"

### `analyzer/` — Competition Analysis

#### `competition.py`

```mermaid
classDiagram
    class CompetitionMetrics {
        +total_historical: int
        +total_analyzed: int
        +total_skipped: int
        +low_competition_count: int
        +competition_ratio: float | None
        +is_interesting: bool
        +is_determinable: bool
    }

    class Calculator {
        +calculate_metrics(analyses, max_participants, ratio_threshold)
        +log_metrics(customer_inn, metrics)
    }

    Calculator --> CompetitionMetrics
```

**Functions:**
- `calculate_metrics(analyses, max_participants, ratio_threshold)` — Calculate competition metrics
- `log_metrics(customer_inn, metrics)` — Log metrics to logger

**Metrics Logic:**
```
is_determinable = total_analyzed > 0
competition_ratio = low_competition_count / total_analyzed
is_interesting = competition_ratio >= ratio_threshold (0.8)
```

### `db/` — Database Layer

#### `schema.py`

```mermaid
erDiagram
    CUSTOMERS ||--o{ TENDERS : "has"
    TENDERS ||--o| PROTOCOL_ANALYSIS : "has"
    CUSTOMERS ||--o{ RESULTS : "has"

    CUSTOMERS {
        string inn PK
        string name
        string status
        datetime last_analysis_date
        datetime created_at
    }

    TENDERS {
        string tender_id PK
        string customer_inn FK
        string url
        string eis_url
        string title
        float price
        datetime publish_date
        string tender_status
        datetime created_at
    }

    PROTOCOL_ANALYSIS {
        int id PK
        string tender_id FK
        string tender_id UK
        int participants_count
        string parse_source
        string parse_status
        string doc_path
        string notes
        datetime analyzed_at
    }

    RESULTS {
        int id PK
        string active_tender_id FK
        string customer_inn FK
        int total_historical
        int total_analyzed
        int total_skipped
        int low_competition_count
        float competition_ratio
        boolean is_interesting
        string source
        datetime created_at
    }
```

**Customer Statuses:**
- `new` — Newly discovered
- `processing` — Being analyzed (historical search)
- `extended_processing` — Extended search in progress
- `extended_analyzed` — Extended analysis completed
- `analyzed` — Analysis completed
- `error` — Error during analysis

#### `repository.py`

**Database Functions:**
- `get_connection()` — Async context manager for DB connection
- `init_db()` — Create tables
- **Customers:** `upsert_customer`, `update_customer_status`, `get_customers_by_status`
- **Tenders:** `upsert_tender`, `get_tenders_by_customer`, `get_active_tenders`, `tender_exists`
- **Protocol Analysis:** `upsert_protocol_analysis`, `get_protocol_analyses_for_customer`, `get_latest_protocol_analyses`
- **Results:** `insert_result`, `get_interesting_results`, `get_interesting_customers`, `result_exists`
- **Reports:** `get_all_customers`, `get_all_results`, `get_all_protocol_analyses`

### `reporter/` — Report Generation

#### `console_report.py`

**Functions:**
- `print_console_report(interesting_results, all_results, all_customers)` — Print console report
- `log_console_summary(total_customers, total_interesting)` — Log summary to file

#### `excel_report.py`

```mermaid
classDiagram
    class ExcelReport {
        +generate_excel_report(interesting_results, all_results, all_customers, all_protocols)
        -_write_interesting_sheet(wb, results)
        -_write_customers_sheet(wb, customers)
        -_write_analysis_details_sheet(wb, protocols, results)
    }
```

**Excel Sheets:**
1. **Интересные тендеры** — Tenders with low competition
2. **Все заказчики** — All customers with tender counts
3. **Детали анализа** — Protocol analysis details

## Data Flow

```mermaid
flowchart LR
    subgraph Input
        keywords["Search Keywords"]
        filters["Price/Date Filters"]
    end

    subgraph Stage1["Stage 1: Active Tenders"]
        scraper1["Scrape rostender.info"]
        extract1["Extract INN"]
    end

    subgraph Stage2["Stage 2: Historical Search"]
        scraper2["Find completed tenders"]
        download["Download protocols"]
    end

    subgraph Stage3["Stage 3: Analysis"]
        parse["Parse documents"]
        analyze["Calculate metrics"]
    end

    subgraph Stage4["Stage 4: Reports"]
        console["Console output"]
        excel["Excel report"]
    end

    Input --> Stage1
    Stage1 --> Stage2
    Stage2 --> Stage3
    Stage3 --> Stage4

    Stage1 --> DB[(SQLite)]
    Stage2 --> DB
    Stage3 --> DB
```

## Usage

```bash
# Run full pipeline
python -m src.main

# Or use the module entry point
python -m src
```

## Dependencies

- **playwright** — Browser automation
- **aiosqlite** — Async SQLite
- **openpyxl** — Excel generation
- **pdfplumber** — PDF text extraction
- **python-docx** — DOCX parsing
- **loguru** — Logging
