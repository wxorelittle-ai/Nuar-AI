"""VK API: сбор стены сообщества и вычисление аналитики.

Чистые parse/analytics-функции тестируются без сети; fetch_* ходят в VK API
(нужен VK_SERVICE_TOKEN). Домен принимается как «nuarrest» или ссылкой.
"""
from __future__ import annotations

import logging
import re
import statistics
from collections import Counter
from datetime import datetime, timezone, timedelta

import httpx

from config.settings import settings
from .models import PostStat, VKAnalytics

log = logging.getLogger("restopulse.social.vk")

VK_API = "https://api.vk.com/method"
TIMEOUT = 20
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Стоп-слова для выделения тем (частые/служебные)
STOPWORDS = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы
по только ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или
ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть
надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж кто этот того
потому этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех
никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая
много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более
всегда конечно всю между это наш вас нам все наши""".split())


def extract_domain(value: str) -> str:
    value = (value or "").strip()
    m = re.search(r"vk\.com/([A-Za-z0-9_.]+)", value)
    if m:
        return m.group(1)
    return value.lstrip("@")


def _api_call(method: str, params: dict) -> dict | None:
    params = {**params, "access_token": settings.vk_service_token,
              "v": settings.vk_api_version or "5.199"}
    try:
        r = httpx.get(f"{VK_API}/{method}", params=params, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        log.warning("VK %s недоступен: %s", method, exc)
        return None
    data = r.json()
    if "error" in data:
        log.warning("VK API error %s: %s", method, data["error"].get("error_msg"))
        return None
    return data.get("response")


def parse_wall(response: dict) -> list[PostStat]:
    out: list[PostStat] = []
    for it in response.get("items", []):
        if it.get("is_pinned"):
            continue
        out.append(PostStat(
            id=str(it.get("id", "")),
            owner_id=int(it.get("owner_id", 0) or 0),
            text=(it.get("text") or "").strip(),
            likes=(it.get("likes") or {}).get("count", 0),
            comments=(it.get("comments") or {}).get("count", 0),
            views=(it.get("views") or {}).get("count", 0),
            date=int(it.get("date", 0) or 0),
        ))
    return out


def top_words(posts: list[PostStat], n: int = 8) -> list[dict]:
    counter: Counter = Counter()
    for p in posts:
        for w in re.findall(r"[А-Яа-яЁё]{4,}", p.text.lower()):
            if w not in STOPWORDS:
                counter[w] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(n)]


def analytics(domain: str, posts: list[PostStat], *, subscribers: int | None = None,
              tz_offset_h: int = 3) -> VKAnalytics:
    """Считает аналитику по списку постов (чистая функция)."""
    a = VKAnalytics(domain=domain, subscribers=subscribers)
    if not posts:
        a.error = "нет постов для анализа"
        return a

    a.ok = True
    a.posts_analyzed = len(posts)

    dates = [p.date for p in posts if p.date]
    if dates:
        span = (max(dates) - min(dates)) / 86400
        a.span_days = round(span, 1)
        if span >= 1:
            a.posts_per_week = round(len(posts) / span * 7, 1)
        else:
            a.posts_per_week = float(len(posts))

    a.avg_likes = round(statistics.mean(p.likes for p in posts), 1)
    a.avg_comments = round(statistics.mean(p.comments for p in posts), 1)
    views = [p.views for p in posts if p.views]
    if views:
        a.avg_views = round(statistics.mean(views), 1)
        if a.avg_views:
            a.engagement_rate = round(a.avg_likes / a.avg_views * 100, 2)

    # По дням недели (в локальном времени)
    for p in posts:
        if not p.date:
            continue
        wd = datetime.fromtimestamp(p.date + tz_offset_h * 3600, tz=timezone.utc).weekday()
        a.by_weekday[wd] += 1
    best = max(range(7), key=lambda i: a.by_weekday[i])
    if a.by_weekday[best] > 0:
        a.best_weekday = WEEKDAYS[best]

    a.top_words = top_words(posts)
    a.top_posts = [p.to_dict() for p in sorted(posts, key=lambda p: p.likes, reverse=True)[:3]]
    return a


def fetch(domain: str, count: int = 100) -> VKAnalytics:
    """Живой сбор: groups.getById (подписчики) + wall.get → аналитика."""
    domain = extract_domain(domain)
    if not domain:
        return VKAnalytics(domain="", error="не указана VK-группа")
    if not settings.vk_service_token:
        return VKAnalytics(domain=domain, error="не задан VK_SERVICE_TOKEN")

    subscribers = None
    grp = _api_call("groups.getById", {"group_id": domain, "fields": "members_count"})
    if grp:
        item = grp["groups"][0] if isinstance(grp, dict) and grp.get("groups") else (grp[0] if isinstance(grp, list) and grp else None)
        if item:
            subscribers = item.get("members_count")

    wall = _api_call("wall.get", {"domain": domain, "count": min(count, 100)})
    if wall is None:
        return VKAnalytics(domain=domain, subscribers=subscribers,
                           error="VK API недоступен или группа закрыта")
    posts = parse_wall(wall)
    return analytics(domain, posts, subscribers=subscribers)
