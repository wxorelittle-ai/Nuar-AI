"""Публикация в сообщество VK через wall.post.

Нужен токен сообщества (или пользователя) с правами wall,manage и числовой
id сообщества. Пост публикуется от имени сообщества (from_group=1).
"""
from __future__ import annotations

import httpx

from config.settings import settings
from .base import PublishResult, PublishError
from .http import make_client

VK_API = "https://api.vk.com/method/wall.post"


def build_request(cfg: dict, text: str):
    """Чистая сборка запроса (тестируется без сети)."""
    token = cfg.get("access_token")
    group_id = str(cfg.get("group_id", "")).lstrip("-")
    if not token:
        raise PublishError("VK: не задан access_token сообщества")
    if not group_id:
        raise PublishError("VK: не задан числовой id сообщества (group_id)")
    params = {
        "owner_id": f"-{group_id}",   # для сообщества owner_id отрицательный
        "from_group": 1,
        "message": text,
        "access_token": token,
        "v": settings.vk_api_version or "5.199",
    }
    return VK_API, params, group_id


def parse_response(data: dict, group_id: str) -> PublishResult:
    if "error" in data:
        msg = data["error"].get("error_msg", "неизвестная ошибка")
        return PublishResult(ok=False, error=f"VK: {msg}")
    post_id = data.get("response", {}).get("post_id")
    if post_id is None:
        return PublishResult(ok=False, error="VK: ответ без post_id")
    return PublishResult(ok=True, external_id=str(post_id),
                         link=f"https://vk.com/wall-{group_id}_{post_id}")


def publish(text: str, cfg: dict | None = None) -> PublishResult:
    cfg = cfg if cfg is not None else _cfg()
    try:
        url, params, group_id = build_request(cfg, text)
    except PublishError as exc:
        return PublishResult(ok=False, error=str(exc))
    try:
        # IPv4 + опциональный прокси (VK обычно доступен и без него)
        with make_client(cfg.get("proxy")) as client:
            r = client.post(url, data=params)
    except httpx.HTTPError as exc:
        return PublishResult(ok=False, error=f"VK: ошибка сети — {exc}")
    if r.status_code != 200:
        return PublishResult(ok=False, error=f"VK: HTTP {r.status_code}")
    return parse_response(r.json(), group_id)


def _cfg() -> dict:
    from config.store import store
    return store.get_channel_config("vk")
