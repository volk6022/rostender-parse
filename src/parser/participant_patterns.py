"""Общие regex-паттерны для извлечения числа участников из текста протоколов.

Используется в docx_parser, pdf_parser, и html_protocol для единообразного
парсинга количества участников / поданных заявок.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class ParticipantParsingResult:
    """Результат извлечения числа участников из одного протокола.

    Новый тип возвращает:
    - count: Итоговое количество (после де-дупликации)
    - numbers: Все найденные номера заявок (для меж-протокольной де-дупликации)
    - method: Описание метода
    - confidence: high | medium | low
    """

    count: int | None
    numbers: list[
        int
    ]  # Все найденные номера заявок (для де-дупликации между протоколами)
    method: str  # Описание способа извлечения
    confidence: str  # high | medium | low


# Обратная совместимость: ParticipantResult — алиас для старого кода.
# Старые поля (count, method, confidence) присутствуют в ParticipantParsingResult,
# поэтому вызывающий код с 3 аргументами продолжит работать.
ParticipantResult = ParticipantParsingResult


# ── Категоризированные заголовки таблиц ──────────────────────────────────────

# Иерархия заголовков для идентификации таблиц с заявками участников.
# Используется в docx_parser._analyze_tables и table_analyzer.
TABLE_HEADERS: dict[str, set[str]] = {
    # Категория: Заявки участников (высший приоритет)
    "заявка": {
        "заявка",
        "поданная заявка",
        "сведения о заявках",
        "реестр заявок",
        "поданные заявки",
        "заявки участников",
        "перечень заявок",
        "заявки",
    },
    # Категория: Участники
    "участник": {
        "участник",
        "наименование участника",
        "сведения об участниках",
        "наименование",
        "наименование организации",
        "организация",
        "претендент",
        "заявитель",
    },
    # Категория: Поставщики
    "поставщик": {
        "поставщик",
        "поставщики",
    },
}

# Плоский набор всех заголовков (для быстрой проверки)
ALL_PARTICIPANT_HEADERS: frozenset[str] = frozenset(
    h for group in TABLE_HEADERS.values() for h in group
)


# ── Regex-паттерны (от наиболее надёжных к наименее) ─────────────────────────

# Группа 1: Прямые указания количества заявок/участников
_DIRECT_COUNT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "Количество поданных заявок: 3"
    (
        re.compile(
            r"(?:количество|кол[\-\.]?\s*во)\s+"
            r"(?:поданных\s+)?(?:заявок|заявлений|предложений)"
            r"\s*[:\-–—]\s*(\d+)",
            re.IGNORECASE,
        ),
        "direct_count_applications",
    ),
    # "Подано 3 заявки" / "Поступило 3 заявки"
    (
        re.compile(
            r"(?:подано|поступило|поступила|получено|зарегистрировано)\s+(\d+)\s+"
            r"(?:заяв[а-яё]*|предложени[а-яё]*|запрос[а-яё]*)",
            re.IGNORECASE,
        ),
        "submitted_N_applications",
    ),
    # "Количество участников: 3" / "Число участников: 3"
    (
        re.compile(
            r"(?:количество|число|кол[\-\.]?\s*во)\s+"
            r"(?:участник[а-яё]*|поставщик[а-яё]*|претендент[а-яё]*)"
            r"\s*[:\-–—]\s*(\d+)",
            re.IGNORECASE,
        ),
        "direct_count_participants",
    ),
    # "Допущено 3 участника" / "Допущен 1 участник"
    (
        re.compile(
            r"(?:допущен[а-яё]*)\s+(\d+)\s+"
            r"(?:участник[а-яё]*|заяв[а-яё]*|предложени[а-яё]*)",
            re.IGNORECASE,
        ),
        "admitted_N_participants",
    ),
    # "3 участника допущены"
    (
        re.compile(
            r"(\d+)\s+(?:участник[а-яё]*|заяв[а-яё]*)\s+"
            r"(?:допущен[а-яё]*|принят[а-яё]*|соответству[а-яё]*)",
            re.IGNORECASE,
        ),
        "N_participants_admitted",
    ),
]

# Группа 2: Нумерованные заявки — ищем максимальный номер
# Паттерн: "заявка №N" / "заявление №N" / "предложение №N"
_NUMBERED_APPLICATION_PATTERN = re.compile(
    r"(?:заявк[аи]|заявление|предложение)\s*"
    r"(?:№|#|N|n)\s*(\d+)",
    re.IGNORECASE,
)

# Паттерн для явного указания номера заявки в контексте (например в таблицах)
APPLICATION_NUMBER_PATTERN = re.compile(
    r"(?:заявк[а-яё]*|заявление)\s*(?:№|#|N|n)\s*(\d+)",
    re.IGNORECASE,
)

# Паттерн для нумерованных строк в таблицах (первая колонка — число)
TABLE_WITH_NUMBERS_PATTERN = re.compile(
    r"^\s*(\d+)\s*[.)]\s+",
    re.MULTILINE,
)

# Группа 3: Нумерованные строки участников в таблицах
# "1. ООО «Рога и копыта»" / "1) АО «Завод»"
_NUMBERED_ROWS_PATTERN = re.compile(
    r"^\s*(\d+)\s*[.)]\s+"
    r"(?:ООО|ОАО|АО|ПАО|ЗАО|ИП|ФГУП|ФГБУ|МУП|ГУП|"
    r"Общество|Акционерное|Индивидуальный|Федеральное|Муниципальное|"
    r"Государственное|Открытое|Закрытое|Публичное)",
    re.IGNORECASE | re.MULTILINE,
)

# Группа 4: Подсчёт уникальных ИНН участников в тексте
_INN_IN_TABLE_PATTERN = re.compile(r"(?:ИНН|инн)\s*[:\s]?\s*(\d{10,12})")

# Группа 5: "единственная заявка" / "единственный участник"
_SINGLE_PARTICIPANT_PATTERN = re.compile(
    r"(?:единственн[а-яё]+)\s+(?:заявк[а-яё]*|участник[а-яё]*|поставщик[а-яё]*|"
    r"предложени[а-яё]*|претендент[а-яё]*)",
    re.IGNORECASE,
)

# Группа 6: "заявок не поступило" / "ни одной заявки"
_ZERO_APPLICATIONS_PATTERN = re.compile(
    r"(?:заявок|заявлений|предложений)\s+"
    r"(?:не\s+)?(?:поступило|подано|получено|зарегистрировано)\s*"
    r"(?:не\s+(?:было|поступило))?"
    r"|ни\s+одн[а-яё]+\s+(?:заявк[а-яё]*|предложени[а-яё]*)"
    r"|(?:не\s+поступило|не\s+подано)\s+(?:ни\s+одн[а-яё]+\s+)?(?:заявк[а-яё]*|предложени[а-яё]*)"
    r"|(?:заявки|заявок|предложения)\s+не\s+поступал[а-яё]*"
    r"|(?:отсутств[а-яё]+)\s+(?:заявк[а-яё]*|участник[а-яё]*)",
    re.IGNORECASE,
)

# Группа 7: "признан(а) несостоявш" — часто означает 0 или 1 участника
_VOID_TENDER_PATTERN = re.compile(
    r"(?:признан[а-яё]*)\s+(?:несостоявш[а-яё]*)",
    re.IGNORECASE,
)


def extract_participants_from_text(text: str) -> ParticipantParsingResult:
    """Извлекает количество участников из текстового содержимого протокола.

    Применяет паттерны в порядке убывания надёжности:
    1. Явное указание количества (высокий приоритет)
    2. Перечисление с номерами "Заявка №N"
    3. Нумерация в таблицах "1. ООО ..."
    4. Уникальные ИНН (низкий приоритет)

    Args:
        text: Текстовое содержимое протокола (из .docx, .pdf, .txt, .htm).

    Returns:
        ParticipantParsingResult с количеством участников и методом извлечения.
        Все паттерны возвращают numbers для меж-протокольной де-дупликации.
    """
    if not text or not text.strip():
        return ParticipantParsingResult(
            count=None, numbers=[], method="empty_text", confidence="low"
        )

    # Группа 1: Прямые указания (высокая надёжность)
    for pattern, method in _DIRECT_COUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            count = int(match.group(1))
            logger.debug(
                "Паттерн '{}': найдено {} участник(ов) [{}]",
                method,
                count,
                match.group(0)[:80],
            )
            numbers = list(range(1, count + 1))
            return ParticipantParsingResult(
                count=count, numbers=numbers, method=method, confidence="high"
            )

    # Группа 6: "Заявок не поступило" → 0 участников
    if _ZERO_APPLICATIONS_PATTERN.search(text):
        logger.debug("Найден паттерн 'заявок не поступило' → 0")
        return ParticipantParsingResult(
            count=0, numbers=[], method="zero_applications", confidence="high"
        )

    # Группа 5: "Единственная заявка" → 1 участник
    if _SINGLE_PARTICIPANT_PATTERN.search(text):
        logger.debug("Найден паттерн 'единственная заявка' → 1")
        return ParticipantParsingResult(
            count=1, numbers=[1], method="single_participant", confidence="high"
        )

    # Группа 2: Нумерованные заявки (средняя надёжность)
    numbered_matches = _NUMBERED_APPLICATION_PATTERN.findall(text)
    if numbered_matches:
        numbers = set(int(n) for n in numbered_matches)  # ДЕ-ДУПЛИКАЦИЯ МЕЖДУ ТЭГОВ
        sorted_numbers = sorted(numbers)
        max_num = max(sorted_numbers) if sorted_numbers else 0
        logger.debug(
            "Нумерованные заявки: найденные номера {}, макс. №{}",
            sorted_numbers,
            max_num,
        )
        return ParticipantParsingResult(
            count=max_num,
            numbers=list(sorted_numbers),
            method="numbered_applications",
            confidence="medium",
        )

    # Группа 3: Нумерованные строки с названиями организаций
    row_matches = _NUMBERED_ROWS_PATTERN.findall(text)
    if row_matches:
        numbers = set(int(n) for n in row_matches)  # ДЕ-ДУПЛИКАЦИЯ
        sorted_numbers = sorted(numbers)
        max_row = max(sorted_numbers) if sorted_numbers else 0
        logger.debug(
            "Нумерованные строки участников: найденные номера {}, макс. №{}",
            sorted_numbers,
            max_row,
        )
        return ParticipantParsingResult(
            count=max_row,
            numbers=list(sorted_numbers),
            method="numbered_org_rows",
            confidence="medium",
        )

    # Группа 4: Подсчёт уникальных ИНН
    inn_matches = _INN_IN_TABLE_PATTERN.findall(text)
    if inn_matches:
        unique_inns = set(inn_matches)
        # Исключаем ИНН заказчика (обычно упоминается 1-2 раза в шапке)
        # Берём все уникальные ИНН — это и заказчик, и участники.
        # Если ИНН больше 1, вычитаем 1 (заказчик).
        count = len(unique_inns)
        if count > 1:
            count -= 1  # Минус ИНН заказчика
        logger.debug(
            "Уникальные ИНН: {} (за вычетом заказчика: {})", len(unique_inns), count
        )
        return ParticipantParsingResult(
            count=count, numbers=[], method="unique_inn_count", confidence="low"
        )

    # Группа 7: "Признана несостоявшейся" — 0 или 1 участник
    if _VOID_TENDER_PATTERN.search(text):
        logger.debug("Тендер признан несостоявшимся → предположительно 1 участник")
        return ParticipantParsingResult(
            count=1, numbers=[1], method="void_tender", confidence="low"
        )

    # Ничего не найдено
    logger.debug("Ни один паттерн не сработал")
    return ParticipantParsingResult(
        count=None, numbers=[], method="no_pattern_matched", confidence="low"
    )
