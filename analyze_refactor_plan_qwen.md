## Rostender Parser Participant Refactor Plan

### Summary
This document explains the refactoring and improvement plan for the participant-counting logic in the Rostender Parser project. The goal is to enhance accuracy, maintain existing functionality, and improve code organization.

### Key Problems with Old Logic
The original logic was ad-hoc, relying heavily on a large, unorganized block of regex patterns without clear priority or context. This led to:
*   **Low Accuracy:** Competitors could easily hide their entries in the text, leading to incorrect counts.
*   **Unreliable Rules:** The single `extract_participants_from_text()` function was difficult to test and maintain.
*   **Code Duplication:** Similar logic existed in both `docx_parser.py` and `pdf_parser.py`, violating DRY principles.
*   **Lack of Structure:** There was no clear hierarchy or documentation for the regex patterns used.

### Our Approach
to address these issues, we will:
1.  Create a **centralized** `analyze_text()` function in `src/parser/participant_patterns.py` that will handle all participant-counting logic.
2.  Organize the old, disparate regex patterns into a clear, prioritized list.
3.  Improve the patterns for greater accuracy and add new ones as needed.
4.  Update both `docx_parser.py` and `pdf_parser.py` to use this new, unified function.
5.  Add comprehensive tests to ensure correctness.

### Step-by-Step Implementation Plan

#### Stage 1: Create the Core Analysis Function

*   **File:** `src/parser/participant_patterns.py`
*   **Goal:** Replace the old, disorganized logic with a single, well-documented `analyze_text(text: str) -> ParticipantResult` function.
*   **Content:** This is where all the magic happens. It will:
    *   Apply a set of regex patterns in a defined order of priority.
    *   Handle special cases like "no applications" or "void tender".
    *   Count unique INNs from tables.
    *   Provide clear `method` and `confidence` values for each step.

#### Stage 2: Organize and Improve the Patterns

*   **File:** `src/parser/participant_patterns.py`
*   **Goal:** Create a clear, prioritized list of regex patterns for extracting participant counts from text.
*   **Content:** We will:
    *   Keep all existing patterns.
    *   Add new ones if needed to cover more cases.
    *   Categorize them by reliability/accuracy.
    *   Document each pattern's purpose and expected use case.

#### Stage 3: Update Parsers to Use the New Logic

*   **File:** `src/parser/docx_parser.py`
*   **Goal:** Modify the DOCX parser to use the new `analyze_text()` function instead of the old logic.
*   **Change:** Update the `extract_participants_from_docx()` function to call `analyze_text(full_text)` instead of the old, direct regex search.

*   **File:** `src/parser/pdf_parser.py`
*   **Goal:** Modify the PDF parser to use the new `analyze_text()` function instead of the old logic.
*   **Change:** Update the `extract_participants_from_pdf()` function to call `analyze_text(full_text)` instead of the old, direct regex search.

#### Stage 4: Add Tests

*   **File:** `tests/test_parser.py`
*   **Goal:** Ensure the refactored code works as expected.
*   **Content:** We will add tests for:
    *   Direct count patterns.
    *   Numbered applications.
    *   Zero applications.
    *   Void tenders.
    *   Unique INN counts.

### Benefits of This Refactor

1.  **Improved Accuracy:** By organizing patterns and adding special cases, our logic will be far less prone to error.
2.  **Easier Maintenance:** All participant-counting logic will be in one place, making it easier to understand, test, and improve upon in the future.
3.  **Reduced Code Duplication:** Both `docx_parser.py` and `pdf_parser.py` will use the same core logic, adhering to the DRY principle.
4.  **Better Structure:** This refactor sets us up for easier expansion and clearer documentation down the line.