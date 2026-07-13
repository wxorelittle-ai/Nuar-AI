"""Публикация в Telegram-канал через Bot API sendMessage.

Нужен токен бота (@BotFather) и канал: @username или числовой chat_id
(вида -100…). Бот должен быть администратором канала.
"""
from __future__ import annotations

import httpx

from config.settings import settings
from .base import PublishResult, PublishError

API_BASE = "https://api.telegram.org"


def build_request(cfg: dict, text: str):
    """Чистая сборка запроса (тестируется без сети)."""
    token = cfg.get("bot_token")
    channel = str(cfg.get("channel", "")).strip()
    if not token:
        raise PublishError("Telegram: не задан токен бота")
    if not channel:
        raise PublishError("Telegram: не задан канал (@username или chat_id)")
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {"chat_id": channel, "text": text, "disable_web_page_preview": True}
    return url, payload, channel


def parse_response(data: dict, channel: str) -> PublishResult:
    if not data.get("ok"):
        return PublishResult(ok=False, error=f"Telegram: {data.get('description', 'ошибка')}")
    res = data.get("result", {})
    msg_id = res.get("message_id")
    link = ""
    if channel.startswith("@") and msg_id is not None:
        link = f"https://t.me/{channel[1:]}/{msg_id}"
    return PublishResult(ok=True, external_id=str(msg_id), link=link)


def publish(text: str, cfg: dict | None = None) -> PublishResult:
    cfg = cfg if cfg is not None else _cfg()
    try:
        url, payload, channel = build_request(cfg, text)
    except PublishError as exc:
        return PublishResult(ok=False, error=str(exc))
    try:
        # local_address="0.0.0.0" принудительно использует IPv4
        with httpx.Client(timeout=settings.request_timeout_sec,
                          transport=httpx.HTTPTransport(local_address="0.0.0.0")) as client:
            r = client.post(url, json=payload)
    except httpx.HTTPError as exc:
        return PublishResult(ok=False, error=f"Telegram: ошибка сети — {exc}")
    if r.status_code != 200:
        try:
            return parse_response(r.json(), channel)
        except Exception:
            return PublishResult(ok=False, error=f"Telegram: HTTP {r.status_code}")
    return parse_response(r.json(), channel)


def _cfg() -> dict:
    from config.store import store
    return store.get_channel_config("telegram")
