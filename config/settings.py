"""Загрузка конфигурации из окружения (.env) и config/competitors.yaml.

Единая точка доступа к настройкам: HTTP-параметры, токены, расписание,
список конкурентов. Нигде больше os.environ напрямую не дёргаем.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Корень пакета restopulse/ (на уровень выше config/)
BASE_DIR = Path(__file__).resolve().parent.parent
COMPETITORS_FILE = BASE_DIR / "config" / "competitors.yaml"
DATA_DIR = BASE_DIR / "data"

# Загружаем .env один раз при импорте (если файл есть)
load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name) or default)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Все настройки приложения, собранные из окружения."""

    # Telegram
    telegram_bot_token: str = field(default_factory=lambda: _get("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _get("TELEGRAM_CHAT_ID"))
    # Прокси для обхода egress-блокировки Telegram у провайдера сервера.
    # Формат: http://host:port , http://user:pass@host:port или socks5://host:port
    # (для socks нужен пакет httpx[socks]). Fallback, если в UI прокси не задан.
    telegram_proxy: str = field(default_factory=lambda: _get("TELEGRAM_PROXY"))

    # VK API
    vk_service_token: str = field(default_factory=lambda: _get("VK_SERVICE_TOKEN"))
    vk_api_version: str = field(default_factory=lambda: _get("VK_API_VERSION", "5.199"))

    # Внешние API-ключи (опциональны)
    dgis_api_key: str = field(default_factory=lambda: _get("DGIS_API_KEY"))
    yandex_api_key: str = field(default_factory=lambda: _get("YANDEX_API_KEY"))

    # HeadHunter (приложение для поиска вакансий; dev.hh.ru)
    hh_client_id: str = field(default_factory=lambda: _get("HH_CLIENT_ID"))
    hh_client_secret: str = field(default_factory=lambda: _get("HH_CLIENT_SECRET"))

    # Хранилище
    database_url: str = field(default_factory=lambda: _get("DATABASE_URL"))

    # Безопасность (вход в панель)
    admin_password: str = field(default_factory=lambda: _get("ADMIN_PASSWORD"))
    secret_key: str = field(default_factory=lambda: _get("SECRET_KEY"))

    # Поведение краулера
    request_delay_sec: float = field(default_factory=lambda: _get_float("REQUEST_DELAY_SEC", 2.0))
    request_timeout_sec: int = field(default_factory=lambda: _get_int("REQUEST_TIMEOUT_SEC", 20))
    http_user_agent: str = field(
        default_factory=lambda: _get(
            "HTTP_USER_AGENT",
            "RestoPulseBot/0.1 (+https://nuar.example; monitoring)",
        )
    )

    # Расписание
    digest_cron_day_of_week: str = field(default_factory=lambda: _get("DIGEST_CRON_DAY_OF_WEEK", "mon"))
    digest_cron_hour: int = field(default_factory=lambda: _get_int("DIGEST_CRON_HOUR", 9))
    digest_cron_minute: int = field(default_factory=lambda: _get_int("DIGEST_CRON_MINUTE", 0))
    timezone: str = field(default_factory=lambda: _get("TIMEZONE", "Asia/Yekaterinburg"))

    @property
    def use_postgres(self) -> bool:
        return bool(self.database_url)


# Единственный экземпляр настроек на процесс
settings = Settings()


def load_competitors_config(path: Path | None = None) -> dict:
    """Читает config/competitors.yaml. Возвращает dict с ключами
    ``competitors`` и ``media_sources``. Бросает понятную ошибку, если
    файл отсутствует или невалиден."""
    path = path or COMPETITORS_FILE
    if not path.exists():
        raise FileNotFoundError(f"Не найден файл конкурентов: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("competitors", [])
    data.setdefault("media_sources", [])
    return data
