"""Отправка сообщений в Telegram через Bot API.

Минимально необходимое: sendMessage управляющему Nuar. Токен и chat_id —
из окружения (.env). Без них send_message честно вернёт False и залогирует.
"""
from __future__ import annotations

import logging

import httpx

from config.settings import settings

log = logging.getLogger("restopulse.telegram")

API_BASE = "https://api.telegram.org"


def send_message(text: str, *, parse_mode: str = "Markdown") -> bool:
    """Отправляет text в чат TELEGRAM_CHAT_ID. Возвращает True при успехе."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.error("Не заданы TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — отправка невозможна")
        return False

    url = f"{API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=settings.request_timeout_sec,
        )
    except httpx.HTTPError as exc:
        log.error("Ошибка сети при отправке в Telegram: %s", exc)
        return False

    if resp.status_code == 200 and resp.json().get("ok"):
        return True
    log.error("Telegram API вернул ошибку: %s %s", resp.status_code, resp.text[:300])
    return False
