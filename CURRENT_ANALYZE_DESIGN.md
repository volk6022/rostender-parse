# Current Analyze Design

## Overview
This document explains the current architecture for participant-counting logic in the Rostender Parser project. The design focuses on accuracy, maintainability, and code reuse.

### Key Components
1.  **`analyze_text(text: str) -> ParticipantResult`**: The core function that performs all participant-counting logic. It uses a prioritized list of regex patterns and handles special cases.
2.  **`ParticipantResult` Data Class**: Stores the output from the analysis, including the final count, the method used, and confidence level.
3.  **Regex Patterns (Prioritized)**: A collection of organized and improved regex expressions for identifying participant counts from text.
4.  **DOCX/PDF Parsers**: Both `docx_parser.py` and `pdf_parser.py` have been updated to use the new `analyze_text()` function instead of their old, direct regex logic.

### Architecture Diagram
Here are visual representations of the design:

#### Class Diagram
diagram LR
    class AnalyzeLogic "Core Logic"
    |
    |---+--( uses )-- regex_patterns
    |      
    |---+--( handles )-- special_cases
    
    class ParticipantResult "Output Object"
    |
    |--- count: int | None
    |--- method: str
    |--- confidence: str
    `

#### Sequence Diagram
diagram LR
    participant User
    participant FunctionCall
    participant AnalyzeLogic
    
    function FunctionCall --> User: analyze_text(text)
    function FunctionCall --> AnalyzeLogic: apply_patterns()
    function AnalyzeLogic -->> FunctionCall: return ParticipantResult
    
### Pattern Details
The patterns are applied in this order of priority:
1.  **Direct Count Patterns:** "...заявок: 3", "Подано 3 заявки"
2.  **Numbered Applications:** "Заявка №3"
3.  **Numbered Organization Rows:** "1. ООО...": found in tables
4.  **Unique INN Count:** From tables with "ИНН" headers
5.  **Single Participant:** "Единственная заявка"
6.  **Zero Applications:** "заявок не поступило"
7.  **Void Tender:** "...неостоявшимся..."

### Design Decisions
*   We chose a centralized function for easier maintenance and testing.
*   Patterns were kept in the same file for simplicity, as they are core to the logic.
*   Both DOCX and PDF parsers now use this single logic function, reducing code duplication.

### Testing & Validation
We will thoroughly test these patterns against a wide range of extracted text samples to ensure accuracy.