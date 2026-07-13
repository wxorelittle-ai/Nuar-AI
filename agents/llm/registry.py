"""Метаданные провайдеров для UI настроек.

Описывает поля каждого провайдера, чтобы фронтенд рисовал формы автоматически.
Здесь же — «человеческие» названия, ссылки на документацию и подсказки.
"""
from __future__ import annotations

# type: "text" | "password" | "bool"
PROVIDERS = [
    {
        "key": "yandexgpt",
        "title": "YandexGPT",
        "subtitle": "Yandex Cloud · Foundation Models",
        "docs": "https://yandex.cloud/ru/docs/foundation-models/",
        "help": "Создайте API-ключ сервисного аккаунта в Yandex Cloud и укажите Folder ID каталога.",
        "fields": [
            {"name": "api_key", "label": "API-ключ", "type": "password", "placeholder": "AQVN…"},
            {"name": "folder_id", "label": "Folder ID (каталог)", "type": "text", "placeholder": "b1g…"},
            {"name": "model", "label": "Модель", "type": "text", "default": "yandexgpt-lite/latest",
             "hint": "напр. yandexgpt/latest или yandexgpt-lite/latest"},
        ],
    },
    {
        "key": "gigachat",
        "title": "GigaChat",
        "subtitle": "Сбер",
        "docs": "https://developers.sber.ru/docs/ru/gigachat/api/overview",
        "help": "В личном кабинете GigaChat получите «Ключ авторизации» (Authorization key, Base64). "
                "Если запрос падает по SSL — отключите проверку сертификата (нужен корневой сертификат Минцифры).",
        "fields": [
            {"name": "authorization_key", "label": "Authorization key (Base64)", "type": "password", "placeholder": "NGE2…"},
            {"name": "scope", "label": "Scope", "type": "text", "default": "GIGACHAT_API_PERS",
             "hint": "GIGACHAT_API_PERS (физлица) · GIGACHAT_API_B2B · GIGACHAT_API_CORP"},
            {"name": "model", "label": "Модель", "type": "text", "default": "GigaChat",
             "hint": "GigaChat · GigaChat-Pro · GigaChat-Max"},
            {"name": "verify_ssl", "label": "Проверять SSL-сертификат", "type": "bool", "default": False},
        ],
    },
    {
        "key": "openai",
        "title": "OpenAI-совместимый",
        "subtitle": "OpenAI · DeepSeek · OpenRouter · локальный",
        "docs": "https://platform.openai.com/docs/api-reference",
        "help": "Подходит любой сервис с OpenAI-совместимым API. Укажите базовый URL и ключ. "
                "Для OpenAI base URL можно оставить по умолчанию.",
        "fields": [
            {"name": "api_key", "label": "API-ключ", "type": "password", "placeholder": "sk-…"},
            {"name": "base_url", "label": "Базовый URL", "type": "text", "default": "https://api.openai.com/v1",
             "hint": "DeepSeek: https://api.deepseek.com · OpenRouter: https://openrouter.ai/api/v1"},
            {"name": "model", "label": "Модель", "type": "text", "default": "gpt-4o-mini"},
        ],
    },
    {
        "key": "claude",
        "title": "Claude",
        "subtitle": "Anthropic",
        "docs": "https://docs.anthropic.com/en/api/messages",
        "help": "Ключ из консоли Anthropic (console.anthropic.com).",
        "fields": [
            {"name": "api_key", "label": "API-ключ", "type": "password", "placeholder": "sk-ant-…"},
            {"name": "model", "label": "Модель", "type": "text", "default": "claude-3-5-sonnet-latest"},
        ],
    },
]

PROVIDER_BY_KEY = {p["key"]: p for p in PROVIDERS}


def default_config(key: str) -> dict:
    """Значения по умолчанию для полей провайдера."""
    p = PROVIDER_BY_KEY.get(key, {})
    out = {}
    for f in p.get("fields", []):
        if "default" in f:
            out[f["name"]] = f["default"]
    return out
