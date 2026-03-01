# Rostender Parser — Project Structure

## Overview

Rostender Parser — это CLI-инструмент для автоматического поиска и анализа государственных тендеров на портале rostender.info. Система авторизуется на сайте, находит активные тендеры, анализирует историю заказчиков и выявляет тендеры с низкой конкуренцией.

## Architecture

```mermaid
flowchart TB
    subgraph CLI["main.py — CLI Entry Point"]
        direction TB
        run["run() async"]
    end

    subgraph ConfigYAML["config.yaml — User Configuration"]
        creds["Credentials (login, password)"]
        search_params["Search Parameters (keywords, prices, dates)"]
        analysis_params["Analysis Parameters (thresholds, limits)"]
        output_params["Output Settings (formats)"]
    end

    subgraph Config["config.py — Configuration Loader"]
        dirs["Paths (DATA_DIR, DOWNLOADS_DIR, REPORTS_DIR)"]
        params["Loaded Parameters from YAML"]
        selectors["CSS Selectors for rostender.info"]
    end

    subgraph Scraper["scraper/ — Web Scraping"]
        auth["auth.py<br/>Login to rostender.info"]
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

    ConfigYAML --> Config
    CLI --> Config
    CLI --> Scraper
    CLI --> Parser
    CLI --> Analyzer
    CLI --> DB
    CLI --> Reporter

    auth --> browser
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

    User->>Browser: Launch pipeline

    Note over Browser,rostender: Single browser session for entire pipeline

    Browser->>rostender: 0. Login (username + password)
    rostender-->>Browser: Session cookies

    Browser->>rostender: 1. Search active tenders
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
    end

    Note over Browser,rostender: Extended search for interesting customers

    loop For each interesting customer
        Browser->>rostender: 5. Search all active tenders (lower price)
        rostender-->>Browser: Extended tender list
        Browser->>DB: Save + analyze new tenders
    end

    DB->>Reporter: 6. Generate report
    Reporter-->>User: Console + Excel output
```

## Configuration

### config.yaml (User Configuration)

All user-configurable parameters are stored in `config.yaml` in the project root. The file is **not committed to git** (contains credentials). A template `config.yaml.example` is provided.

```yaml
# Authentication (required)
rostender_login: "your_login"
rostender_password: "your_password"

# Search parameters, price thresholds, analysis settings, output formats...
```

### config.py (Configuration Loader)

Loads `config.yaml` and exports typed constants for use by other modules.

| Component | Source | Description |
|-----------|--------|-------------|
| **Credentials** | YAML | `ROSTENDER_LOGIN`, `ROSTENDER_PASSWORD` (required, validated at startup) |
| **Paths** | Computed | `PROJECT_ROOT`, `DATA_DIR`, `DOWNLOADS_DIR`, `REPORTS_DIR`, `DB_PATH` |
| **Search Keywords** | YAML | `SEARCH_KEYWORDS`, `EXCLUDE_KEYWORDS` |
| **Price Limits** | YAML | `MIN_PRICE_ACTIVE` (25M), `MIN_PRICE_RELATED` (2M), `MIN_PRICE_HISTORICAL` (1M) |
| **Analysis Thresholds** | YAML | `MAX_PARTICIPANTS_THRESHOLD` (2), `COMPETITION_RATIO_THRESHOLD` (0.8) |
| **Selectors** | Python | CSS selectors for rostender.info page elements (including login form) |

**Startup validation:**
- If `config.yaml` is missing → error with instructions to copy from `config.yaml.example`
- If `rostender_login` or `rostender_password` is empty → error at startup

## Module Details

### `scraper/` — Web Scraping

#### `auth.py`

```mermaid
classDiagram
    class Auth {
        +login(page) async
    }
    Auth --> Page
```

**Functions:**
- `login(page)` — Authenticate on rostender.info. Navigates to `/login`, fills username/password from config, submits the form, verifies success by checking that `.header--notLogged` disappears. Raises `RuntimeError` on failure.

**Login form selectors:**
| Selector | Target |
|----------|--------|
| `#username` | Login/email field |
| `#password` | Password field |
| `button[name='login-button']` | Submit button |
| `.header--notLogged` | Marker for unauthenticated state |

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

**Session architecture:** The pipeline uses a single `Browser` → single `BrowserContext` → single `Page` for the entire run. Login is performed once; cookies persist across all navigation within the session.

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
- `analyzed` — Analysis completed
- `extended_processing` — Extended search in progress
- `extended_analyzed` — Extended analysis completed
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
        config["config.yaml<br/>(credentials + params)"]
        cli_args["CLI Arguments<br/>(optional overrides)"]
    end

    subgraph Stage0["Stage 0: Auth"]
        login["Login to rostender.info"]
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

    subgraph Stage3ext["Stage 3+: Extended Search"]
        extended["Find more tenders<br/>for interesting customers"]
    end

    subgraph Stage4["Stage 4: Reports"]
        console["Console output"]
        excel["Excel report"]
    end

    Input --> Stage0
    Stage0 --> Stage1
    Stage1 --> Stage2
    Stage2 --> Stage3
    Stage3 --> Stage3ext
    Stage3ext --> Stage4

    Stage1 --> DB[(SQLite)]
    Stage2 --> DB
    Stage3 --> DB
    Stage3ext --> DB
```

## File Structure

```
rostender-parse/
├── .gitignore
├── pyproject.toml            # Dependencies & entry point
├── pytest.ini                # Test configuration
├── uv.lock                   # UV lockfile
├── README.md                 # User documentation
├── STRUCTURE.md              # Architecture documentation (this file)
├── login_config_plan.md      # Implementation plan for auth & config
│
├── config.yaml.example       # Configuration template (committed to git)
├── config.yaml               # Active configuration (NOT in git, contains credentials)
│
├── data/                     # Runtime data
│   ├── rostender.db          # SQLite database
│   └── rostender.log         # Application log
│
├── downloads/                # Downloaded protocol files
│
├── reports/                  # Generated Excel reports
│
├── src/
│   ├── __init__.py
│   ├── config.py             # Configuration loader (reads config.yaml)
│   ├── main.py               # CLI entry point, pipeline orchestration
│   │
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── auth.py           # Authentication on rostender.info
│   │   ├── browser.py        # Playwright browser lifecycle
│   │   ├── active_tenders.py # Search & parse active tenders
│   │   ├── historical_search.py  # Search completed tenders by INN
│   │   └── eis_fallback.py   # Fallback to zakupki.gov.ru
│   │
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── html_protocol.py  # Protocol analysis pipeline
│   │   ├── pdf_parser.py     # PDF text extraction
│   │   ├── docx_parser.py    # DOCX parsing
│   │   └── participant_patterns.py  # Shared regex patterns
│   │
│   ├── analyzer/
│   │   ├── __init__.py
│   │   └── competition.py    # Competition metrics calculation
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.py         # SQLite DDL
│   │   └── repository.py     # Async CRUD operations
│   │
│   └── reporter/
│       ├── __init__.py
│       ├── console_report.py # Console output formatting
│       └── excel_report.py   # Excel .xlsx generation
│
└── tests/
    ├── __init__.py
    ├── conftest.py            # Fixtures: MockRow, sample data, in-memory DB
    ├── test_parser.py         # Tests for participant_patterns.py
    ├── test_analyzer.py       # Tests for competition.py
    └── test_repository.py     # Tests for repository.py
```

## Dependencies

- **playwright** — Browser automation (headless Chromium)
- **aiosqlite** — Async SQLite
- **openpyxl** — Excel generation
- **pdfplumber** — PDF text extraction
- **python-docx** — DOCX parsing
- **loguru** — Structured logging
- **pyyaml** — YAML configuration loading

## Usage

```bash
# First-time setup
cp config.yaml.example config.yaml
# Edit config.yaml: fill in rostender_login and rostender_password

# Run full pipeline
rostender

# Or directly
python -m src.main

# Check parameters without launching browser
rostender --dry-run

# Override config values via CLI
rostender --keywords Поставка Оборудование --min-price 10000000 --days-back 14
```
