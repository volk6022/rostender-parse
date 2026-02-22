"""Настраиваемые параметры проекта Rostender Parser."""

from pathlib import Path

# ── Пути ────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
REPORTS_DIR = PROJECT_ROOT / "reports"
DB_PATH = DATA_DIR / "rostender.db"

# ── Поиск активных тендеров ─────────────────────────────────────────────────────
SEARCH_KEYWORDS: list[str] = [
    "Поставка",
    "Поставки",
    "Поставке",
    "Закупка",
    "Снабжение",
    "Приобретение",
    "Оборудование и материалы",
    "Оборудование",
    "Станок",
    "Станки",
]

EXCLUDE_KEYWORDS: list[str] = [
    "Выполнение работ",
    "Капитальный ремонт",
    "Оказание услуг",
    "Поставка лекарственных препаратов",
    "Благоустройство",
    "Предоставление субсидий",
    "Аренда",
    "Строительство",
    "Отбор получателей субсидии",
    "Возмещение",
    "Оказание консультационных услуг",
    "Лекарственного препарата",
    "Выполнение строительно-монтажных работ",
]

# Диапазон дат публикации для поиска (формат "DD.MM.YYYY").
# None — «сегодня».  Можно задать явно: "01.02.2026"
SEARCH_DATE_FROM: str | None = None
SEARCH_DATE_TO: str | None = None

MIN_PRICE_ACTIVE: int = 25_000_000  # Мин. цена активных тендеров (Этап 1)
MIN_PRICE_RELATED: int = 2_000_000  # Мин. цена доп. тендеров заказчика (Этап 3)
MIN_PRICE_HISTORICAL: int = 1_000_000  # Мин. цена при поиске исторических (Этап 2)

# ── Анализ конкуренции ──────────────────────────────────────────────────────────
HISTORICAL_TENDERS_LIMIT: int = 5  # Кол-во последних завершённых для анализа
MAX_PARTICIPANTS_THRESHOLD: int = 2  # Макс. участников для «низкой конкуренции»
COMPETITION_RATIO_THRESHOLD: float = 0.8  # Доля тендеров с низкой конкуренцией

# ── Хранение ────────────────────────────────────────────────────────────────────
KEEP_DOWNLOADED_DOCS: bool = True  # Сохранять документы после анализа
CLEANUP_AFTER_DAYS: int = 30  # Через сколько дней чистить старые файлы

# ── Выход ───────────────────────────────────────────────────────────────────────
OUTPUT_FORMATS: list[str] = ["console", "excel"]

# ── CSS-селекторы rostender.info ─────────────────────────────────────────────
# Вынесены в одно место: при изменении вёрстки сайта правки только здесь.
SELECTORS: dict[str, str] = {
    # Страница расширенного поиска
    "search_keywords_input": "#keywords",
    "search_exceptions_input": "#exceptions",
    "search_min_price": "#min_price",
    "search_min_price_disp": "#min_price-disp",
    "search_hide_price": "#hide_price",
    "search_states": "#states",
    "search_placement_ways": "#placement_ways",
    "search_date_from": "#tender-start-date-from",
    "search_date_to": "#tender-start-date-to",
    "search_button": "#start-search-button",
    # Список результатов
    "tender_card": "article.tender-row",
    "tender_link": "a.tender-info__description",
    "tender_link_alt": "a.tender-info__link",
    "tender_price": ".starting-price__price",
    "pagination_next": "ul.pagination > li.last > a",
    # Страница тендера
    "inn_button": ".toggle-counterparty",
    "eis_link": "a[href*='zakupki.gov.ru']",
    # Поле «Заказчик» (ИНН или наименование)
    "search_customers_input": "#customers",
}
