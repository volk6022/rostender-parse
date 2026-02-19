# Implementation Plan: Rostender Parser

## 1. Architecture & Tech Stack
*   **Language:** Python 3.10+
*   **Browser Automation:** Playwright (Async API)
*   **Database:** SQLite (via `aiosqlite` for async support)
*   **Document Parsing:** 
    *   `python-docx` for .doc/.docx
    *   `pdfplumber` or `pypdf` for text-based PDF
*   **Scheduling/Queue:** Internal async queues (no external Redis required for this scale)

## 2. Database Schema (SQLite)

We need relational data to track customers and prevent re-analysis.

```sql
-- Tracks unique customers (agencies)
CREATE TABLE IF NOT EXISTS customers (
    inn TEXT PRIMARY KEY,
    name TEXT,
    status TEXT DEFAULT 'new', -- new, processing, analyzed, ignored, error
    last_analysis_date DATETIME,
    avg_participants FLOAT, -- Cached metric from historical analysis
    is_interesting BOOLEAN DEFAULT 0 -- True if they meet the "low competition" criteria
);

-- Tracks specific tenders (both active and historical)
CREATE TABLE IF NOT EXISTS tenders (
    tender_id TEXT PRIMARY KEY, -- Rostender ID or EIS number
    customer_inn TEXT,
    url TEXT,
    status TEXT, -- active, completed
    title TEXT,
    price REAL,
    publish_date DATETIME,
    participants_count INTEGER NULL, -- NULL = unknown
    doc_parsing_status TEXT, -- pending, success, failed, no_docs
    FOREIGN KEY(customer_inn) REFERENCES customers(inn)
);
```

## 3. Module Breakdown

### Module A: Active Tender Discovery (Scraper)
**Goal:** Populate the `tenders` table with active tenders and `customers` table with new INNs.

1.  **Input:** Search filters defined in `technical_specifications.md` (Keywords: "Поставка", Price > 25m, etc.).
2.  **Process:**
    *   Launch Playwright.
    *   Navigate to Rostender search with filters applied.
    *   Iterate through search results pages.
    *   For each tender:
        *   Extract Tender ID, Title, Price, URL.
        *   Visit Tender Page (or extract from list if possible) to get **Customer INN**.
        *   **Check DB:** 
            *   If Customer exists and `last_analysis_date` is recent -> Link tender, skip analysis.
            *   If Customer is new -> Add to DB with status 'new'.

### Module B: Historical Analysis (The Core Logic)
**Goal:** Determine if a customer has a history of low competition.

1.  **Selection:** Select customers from DB where `status = 'new'`.
2.  **Search Completed Tenders:**
    *   For each customer, perform a *new search* on Rostender.
    *   Filters: Status="Completed", Customer INN, Keywords (variants of "Поставка", "Оборудование").
    *   Limit: Fetch last **5-10** relevant completed tenders.
3.  **Process Each Historical Tender:**
    *   **Step 3.1: Check HTML Protocol.** Some sites list participants directly in the HTML table "Протокол". If found -> Save count, Done.
    *   **Step 3.2: Download Documents.** If HTML is empty, look for attachments.
        *   Keywords: "Протокол", "Итоги", "Рассмотрение".
        *   Priority: `.docx` > `.doc` > `.pdf` (text).
        *   **EIS Fallback:** If documents are missing/broken on Rostender, follow the link to `zakupki.gov.ru` and scrape documents there.
    *   **Step 3.3: Parse Documents.**
        *   **DOCX:** Search for tables. Count rows in tables containing "Участник" or look for text patterns "Количество поданных заявок: X".
        *   **PDF:** Extract text. Search for regex patterns `r"Количество (?:заявок|участников).*?(\d+)"`.
    *   **Step 3.4: Store Result.** Save `participants_count` to `tenders` table. If indeterminable, set specific flag but do not fail the whole customer.

### Module C: Decision & Reporting
1.  **Aggregator:**
    *   Calculate metrics for the customer based on the 3-5 analyzed historical tenders.
    *   Condition: If `(count(tenders_with_<=2_participants) / count(total_analyzed)) >= Threshold` -> Mark Customer as `is_interesting = True`.
2.  **Output:**
    *   Generate a list of *active* tenders belonging to `is_interesting` customers.

## 4. Error Handling & Edge Cases
*   **Captcha:** Rostender may show captchas. *Strategy:* Manual intervention pause or slower requests + browser headers.
*   **Bad Docs:** If a document is a scan (image PDF), log "OCR required - skipped" and treat as "Unknown participants".
*   **EIS Redirection:** Handle intermediate pages when clicking "Link to EIS".

## 5. Development Stages
1.  **Stage 1:** Setup DB and "Active Tender Discovery" (Module A).
2.  **Stage 2:** Implement "Historical Search" and basic "HTML Protocol" parsing.
3.  **Stage 3:** Implement "Document Downloader" (including EIS fallback).
4.  **Stage 4:** Implement "Document Parser" (Docx/PDF text mining).
5.  **Stage 5:** Integration and Reporting.
