"""Настраиваемые параметры проекта Rostender Parser.

Все пользовательские параметры загружаются из config.yaml в корне проекта.
Пути и CSS-селекторы вычисляются/хранятся в Python.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml


_logger = logging.getLogger(__name__)

# ── Пути (вычисляемые, не в YAML) ───────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
REPORTS_DIR = PROJECT_ROOT / "reports"
DB_PATH = DATA_DIR / "rostender.db"

# ── Загрузка config.yaml ────────────────────────────────────────────────────
_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
_EXAMPLE_PATH = PROJECT_ROOT / "config.yaml.example"


# ── Настройка браузера и задержек ───────────────────────────────────────────
BASE_URL = "https://rostender.info"
# Таймаут навигации по умолчанию (мс).
DEFAULT_TIMEOUT = 60_000
# Пауза между запросами для снижения нагрузки на сервер (сек).
POLITE_DELAY = 2.0


class ConfigError(Exception):
    """Ошибка конфигурации — файл не найден, неверный формат или пустые поля."""


def _load_config() -> dict:
    """Загрузить конфигурацию из config.yaml.

    Возвращает пустой словарь, если файл отсутствует (позволяет импортировать
    модуль в тестах без config.yaml).  Полная валидация — через
    :func:`validate_config`.
    """
    if not _CONFIG_PATH.exists():
        _logger.warning(
            "config.yaml не найден (%s). "
            "Используются значения по умолчанию. "
            "Вызовите validate_config() перед запуском pipeline.",
            _CONFIG_PATH,
        )
        return {}

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        _logger.warning(
            "config.yaml имеет неверный формат (ожидается YAML-словарь). "
            "Используются значения по умолчанию."
        )
        return {}

    return cfg


_cfg = _load_config()

# ── Авторизация (обязательно для работы, но не при импорте) ───────────────
ROSTENDER_LOGIN: str = _cfg.get("rostender_login", "")
ROSTENDER_PASSWORD: str = _cfg.get("rostender_password", "")


def validate_config() -> None:
    """Проверить, что обязательные поля конфигурации заполнены.

    Вызывается из ``main()`` перед запуском pipeline.
    Бросает :class:`ConfigError` при ошибках, а не ``sys.exit()`` — это
    позволяет безопасно импортировать ``src.config`` из тестов.

    Raises:
        ConfigError: если config.yaml отсутствует, имеет неверный формат,
            или обязательные поля пусты.
    """
    if not _CONFIG_PATH.exists():
        raise ConfigError(
            f"Файл конфигурации не найден: {_CONFIG_PATH}\n"
            f"Скопируйте шаблон и заполните данные для входа:\n"
            f"  cp {_EXAMPLE_PATH.name} {_CONFIG_PATH.name}"
        )

    if not ROSTENDER_LOGIN or not ROSTENDER_PASSWORD:
        raise ConfigError(
            "rostender_login и rostender_password обязательны в config.yaml.\n"
            "Укажите логин и пароль от rostender.info."
        )


# ── Прокси (опционально) ──────────────────────────────────────────────────────
_proxy_server: str = _cfg.get("proxy_server", "")
_proxy_username: str = _cfg.get("proxy_username", "")
_proxy_password: str = _cfg.get("proxy_password", "")

PROXY_CONFIG: dict | None = None
if _proxy_server:
    PROXY_CONFIG = {"server": _proxy_server}
    if _proxy_username:
        PROXY_CONFIG["username"] = _proxy_username
    if _proxy_password:
        PROXY_CONFIG["password"] = _proxy_password

# ── Поиск активных тендеров ──────────────────────────────────────────────────
SEARCH_KEYWORDS: list[str] = _cfg.get(
    "search_keywords",
    [
        "Поставка",
        "Поставки",
        "Закупка",
        "Снабжение",
        "Приобретение",
        "Оборудование и материалы",
        "Оборудование",
        "Станок",
        "Станки",
        "Лист",
        "Труба",
    ],
)

EXCLUDE_KEYWORDS: list[str] = _cfg.get(
    "exclude_keywords",
    [
        "Выполнение работ",
        "Капитальный ремонт",
        "Оказание услуг",
        "Лекарственные препараты",
        "Благоустройство",
        "Предоставление субсидий",
        "Аренда",
        "Строительство",
        "Отбор получателей субсидии",
        "Возмещение",
        "Оказание консультационных услуг",
        "Лекарственного препарата",
        "Выполнение строительно-монтажных работ",
    ],
)

# Диапазон дат публикации для поиска (формат "DD.MM.YYYY").
# None — «сегодня».
SEARCH_DATE_FROM: str | None = _cfg.get("search_date_from")
SEARCH_DATE_TO: str | None = _cfg.get("search_date_to")

# ── Пороги цен (руб.) ───────────────────────────────────────────────────────
MIN_PRICE_ACTIVE: int = _cfg.get("min_price_active", 25_000_000)
MIN_PRICE_RELATED: int = _cfg.get("min_price_related", 2_000_000)
MIN_PRICE_HISTORICAL: int = _cfg.get("min_price_historical", 1_000_000)

# ── Анализ конкуренции ───────────────────────────────────────────────────────
HISTORICAL_TENDERS_LIMIT: int = _cfg.get("historical_tenders_limit", 5)
MAX_PARTICIPANTS_THRESHOLD: int = _cfg.get("max_participants_threshold", 2)
COMPETITION_RATIO_THRESHOLD: float = _cfg.get("competition_ratio_threshold", 0.8)

# ── Хранение ────────────────────────────────────────────────────────────────
KEEP_DOWNLOADED_DOCS: bool = _cfg.get("keep_downloaded_docs", True)
CLEANUP_AFTER_DAYS: int = _cfg.get("cleanup_after_days", 30)

# ── Выход ───────────────────────────────────────────────────────────────────
OUTPUT_FORMATS: list[str] = _cfg.get("output_formats", ["console", "excel"])

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
    # Авторизация
    "login_username": "#username",
    "login_password": "#password",
    "login_button": "button[name='login-button']",
    "logged_in_marker": ".header--notLogged",
}
