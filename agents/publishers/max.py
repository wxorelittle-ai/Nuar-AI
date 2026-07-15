"""Публикация в MAX (messenger) через Bot API.

Официальный API: https://dev.max.ru/docs-api
  • база: https://platform-api2.max.ru
  • авторизация: HTTP-заголовок ``Authorization: <token>`` (query-токен больше
    не поддерживается);
  • отправка: ``POST /messages?chat_id=<id>`` с телом ``{text, format}``;
  • проверка: ``GET /me``.

Нужен токен бота (@MasterBot → /create) и числовой chat_id канала/чата, куда
бот добавлен. MAX доступен из РФ без прокси — запасной канал к Telegram.
"""
from __future__ import annotations

import httpx

from config.settings import settings
from .base import PublishResult, PublishError
from .http import make_client

API_BASE = "https://platform-api2.max.ru"


def build_request(cfg: dict, text: str):
    """Чистая сборка запроса (тестируется без сети).

    Возвращает (url, headers, params, json_body, chat_id).
    """
    token = (cfg.get("access_token") or "").strip()
    chat_id = str(cfg.get("chat_id", "")).strip()
    if not token:
        raise PublishError("MAX: не задан токен бота")
    if not chat_id:
        raise PublishError("MAX: не задан числовой chat_id канала/чата")
    url = f"{API_BASE}/messages"
    headers = {"Authorization": token}
    params = {"chat_id": chat_id}
    body = {"text": text, "format": "markdown"}
    return url, headers, params, body, chat_id


def parse_response(status: int, data: dict, chat_id: str) -> PublishResult:
    # Успех: {"message": {...}} (объект). Ошибка: {"code": "...", "message": "..."}
    msg = data.get("message")
    if isinstance(msg, dict):
        mid = (msg.get("body") or {}).get("mid", "")
        return PublishResult(ok=True, external_id=str(mid))
    if data.get("code") or isinstance(msg, str):
        return PublishResult(ok=False, error=f"MAX: {msg or data.get('code')}")
    if status != 200:
        return PublishResult(ok=False, error=f"MAX: HTTP {status}")
    return PublishResult(ok=False, error="MAX: неожиданный ответ")


def publish(text: str, cfg: dict | None = None) -> PublishResult:
    cfg = cfg if cfg is not None else _cfg()
    try:
        url, headers, params, body, chat_id = build_request(cfg, text)
    except PublishError as exc:
        return PublishResult(ok=False, error=str(exc))
    try:
        with make_client(cfg.get("proxy")) as client:
            r = client.post(url, headers=headers, params=params, json=body)
    except httpx.HTTPError as exc:
        return PublishResult(ok=False, error=f"MAX: ошибка сети — {exc}")
    try:
        data = r.json()
    except Exception:
        return PublishResult(ok=False, error=f"MAX: HTTP {r.status_code}")
    return parse_response(r.status_code, data, chat_id)


def check(cfg: dict | None = None) -> PublishResult:
    """Проверка подключения: GET /me (не публикует ничего)."""
    cfg = cfg if cfg is not None else _cfg()
    token = (cfg.get("access_token") or "").strip()
    if not token:
        return PublishResult(ok=False, error="MAX: не задан токен бота")
    try:
        with make_client(cfg.get("proxy")) as client:
            r = client.get(f"{API_BASE}/me", headers={"Authorization": token})
    except httpx.HTTPError as exc:
        return PublishResult(ok=False, error=f"MAX: ошибка сети — {exc}")
    try:
        data = r.json()
    except Exception:
        return PublishResult(ok=False, error=f"MAX: HTTP {r.status_code}")
    if data.get("code") or r.status_code != 200:
        return PublishResult(ok=False, error=f"MAX: {data.get('message') or ('HTTP ' + str(r.status_code))}")
    name = data.get("name") or data.get("username") or ""
    return PublishResult(ok=True, external_id=str(name))


def _cfg() -> dict:
    from config.store import store
    return store.get_channel_config("max")
