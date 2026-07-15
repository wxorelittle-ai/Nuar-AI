"""Хранилище пользовательских настроек (редактируются через UI).

Отдельно от config/settings.py (там — инфраструктура из .env). Здесь —
то, что владелец задаёт сам:
  • providers — API-ключи AI-ассистентов + активный провайдер;
  • channels  — подключение соцсетей для публикации (VK, Telegram).

Пишется в data/settings.json (в git не коммитится). Секретные поля (ключи,
токены) никогда не отдаются клиенту целиком — только признак «задан» и подсказка
из последних символов. При сохранении пустое секретное поле НЕ затирает уже
сохранённое значение.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from config.settings import DATA_DIR

_LOCK = threading.Lock()


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "settings.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── низкоуровневое чтение/запись (PostgreSQL или JSON-файл) ───────
    @staticmethod
    def _defaults(data: dict) -> dict:
        data = data or {}
        data.setdefault("active_provider", "")
        data.setdefault("providers", {})
        data.setdefault("channels", {})
        return data

    def _load(self) -> dict:
        from db import database
        if database.db_enabled():
            return self._defaults(database.kv_get("settings"))
        if not self.path.exists():
            return self._defaults({})
        try:
            return self._defaults(json.loads(self.path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return self._defaults({})

    def _save(self, data: dict) -> None:
        from db import database
        if database.db_enabled():
            database.kv_set("settings", data)
            return
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _merge_section(self, data: dict, section: str, patch: dict, secret_fields: dict) -> None:
        items = data.setdefault(section, {})
        for key, fields in (patch or {}).items():
            cur = items.setdefault(key, {})
            secret = secret_fields.get(key, set())
            for field, value in fields.items():
                if field in secret and (value is None or value == ""):
                    continue  # не затираем сохранённый секрет
                cur[field] = value

    # ── провайдеры LLM ────────────────────────────────────────────────
    def get_provider_config(self, key: str) -> dict:
        return self._load().get("providers", {}).get(key, {}) or {}

    def active_provider(self) -> str:
        return self._load().get("active_provider", "")

    def update(self, active_provider: str | None, providers_patch: dict[str, dict]) -> None:
        with _LOCK:
            data = self._load()
            if active_provider is not None:
                data["active_provider"] = active_provider
            self._merge_section(data, "providers", providers_patch, SECRET_FIELDS)
            self._save(data)

    # ── каналы публикации (соцсети) ───────────────────────────────────
    def get_channel_config(self, key: str) -> dict:
        return self._load().get("channels", {}).get(key, {}) or {}

    def update_channels(self, channels_patch: dict[str, dict]) -> None:
        with _LOCK:
            data = self._load()
            self._merge_section(data, "channels", channels_patch, CHANNEL_SECRET_FIELDS)
            self._save(data)


# Какие поля считаются секретными (маскируются) — LLM-провайдеры
SECRET_FIELDS: dict[str, set[str]] = {
    "yandexgpt": {"api_key"},
    "gigachat": {"authorization_key"},
    "openai": {"api_key"},
    "claude": {"api_key"},
}

# Секретные поля каналов публикации
CHANNEL_SECRET_FIELDS: dict[str, set[str]] = {
    "vk": {"access_token"},
    "telegram": {"bot_token"},
    "max": {"access_token"},
}


def mask_secret(value: str) -> dict:
    """Возвращает безопасное представление секрета для UI."""
    if not value:
        return {"set": False, "hint": ""}
    tail = value[-4:] if len(value) >= 4 else "•" * len(value)
    return {"set": True, "hint": f"…{tail}"}


# Единственный экземпляр на процесс
store = SettingsStore()
