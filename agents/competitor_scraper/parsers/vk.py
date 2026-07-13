"""Парсер VK через официальный VK API.

Собирает по открытой группе конкурента:
  • число подписчиков (groups.getById, поле members_count)
  • посты за последние 7 дней и текст самого свежего (wall.get)

Требует сервисный ключ доступа (VK_SERVICE_TOKEN). Без ключа или без
vk_domain у конкурента возвращает SourceSnapshot(ok=False) — не выдумывает.
"""
from __future__ import annotations

import logging

from config.settings import settings
from models.competitor import Competitor, SourceSnapshot
from .http import get

log = logging.getLogger("restopulse.parser.vk")

VK_API = "https://api.vk.com/method"
WEEK_SECONDS = 7 * 24 * 3600


def _api_call(method: str, params: dict) -> dict | None:
    """Вызов метода VK API. Возвращает содержимое поля ``response`` или None."""
    params = {
        **params,
        "access_token": settings.vk_service_token,
        "v": settings.vk_api_version,
    }
    resp = get(f"{VK_API}/{method}", params=params, respect_robots=False)
    if resp is None:
        return None
    data = resp.json()
    if "error" in data:
        log.warning("VK API error %s: %s", method, data["error"].get("error_msg"))
        return None
    return data.get("response")


def fetch(competitor: Competitor, *, now_ts: int) -> SourceSnapshot:
    """Собирает VK-метрики конкурента. ``now_ts`` — текущее unix-время (передаётся
    снаружи, чтобы окно «за неделю» было детерминированным для тестов)."""
    snap = SourceSnapshot(source="vk")

    if not competitor.vk_domain:
        snap.error = "не задан vk_domain"
        return snap
    if not settings.vk_service_token:
        snap.error = "не задан VK_SERVICE_TOKEN"
        return snap

    # 1) Подписчики
    group = _api_call("groups.getById", {"group_id": competitor.vk_domain, "fields": "members_count"})
    if group:
        # API v5.199 отдаёт {"groups": [...]}; более старые — список
        item = None
        if isinstance(group, dict) and group.get("groups"):
            item = group["groups"][0]
        elif isinstance(group, list) and group:
            item = group[0]
        if item:
            snap.subscribers = item.get("members_count")

    # 2) Стена: последние посты
    wall = _api_call("wall.get", {"domain": competitor.vk_domain, "count": 30})
    if wall is None and snap.subscribers is None:
        snap.error = "VK API недоступен или группа закрыта"
        return snap

    if wall and "items" in wall:
        items = wall["items"]
        week_ago = now_ts - WEEK_SECONDS
        # Не считаем закреплённый пост как «пост недели», если он старый
        fresh = [p for p in items if p.get("date", 0) >= week_ago and not p.get("is_pinned")]
        snap.posts_last_week = len(fresh)
        if items:
            newest = max(items, key=lambda p: p.get("date", 0))
            snap.latest_post_text = (newest.get("text") or "").strip()[:400]

    snap.ok = snap.subscribers is not None or snap.posts_last_week is not None
    if not snap.ok:
        snap.error = "VK не вернул данных"
    return snap
