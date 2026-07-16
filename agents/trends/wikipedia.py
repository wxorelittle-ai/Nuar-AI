"""Клиент Wikipedia Pageviews API + вычисление тренда.

Чистые parse/trend-функции тестируются без сети; fetch_* ходят в API.
Требуется осмысленный User-Agent (правило Wikimedia).
"""
from __future__ import annotations

import logging
from statistics import mean
from urllib.parse import quote

import httpx

from .models import TopicTrend

log = logging.getLogger("restopulse.trends.wiki")

API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
PROJECT = "ru.wikipedia"
TIMEOUT = 20
UP_THRESHOLD = 15.0     # % — считаем восходящим/нисходящим трендом

# Пороги окна
MIN_POINTS = 14


def _headers() -> dict:
    return {"User-Agent": "METR-trends/0.1 (restaurant analytics; contact: metr@example.ru)"}


def build_url(article: str, start: str, end: str, project: str = PROJECT) -> str:
    art = quote(article.replace(" ", "_"), safe="")
    return f"{API}/{project}/all-access/all-agents/{art}/daily/{start}/{end}"


def parse_series(data: dict) -> list[int]:
    return [int(it.get("views", 0) or 0) for it in data.get("items", [])]


def _bucket(views: list[int], n: int = 10) -> list[int]:
    if not views:
        return []
    size = max(1, len(views) // n)
    out = [sum(views[i:i + size]) for i in range(0, len(views), size)]
    return out[:n] if len(out) > n else out


def trend_from_series(views: list[int]) -> dict:
    """Считает прирост интереса по дневному ряду просмотров."""
    if len(views) < MIN_POINTS:
        return {"ok": False, "error": "мало данных"}
    half = len(views) // 2
    prior = mean(views[:half]) or 0.0
    recent = mean(views[half:]) or 0.0
    growth = round((recent - prior) / max(prior, 1) * 100, 1)
    direction = "up" if growth >= UP_THRESHOLD else ("down" if growth <= -UP_THRESHOLD else "flat")
    return {
        "ok": True, "prior_avg": round(prior, 1), "recent_avg": round(recent, 1),
        "growth": growth, "direction": direction, "spark": _bucket(views),
    }


def fetch_topic(topic: str, start: str, end: str, project: str = PROJECT) -> TopicTrend:
    url = build_url(topic, start, end, project)
    try:
        r = httpx.get(url, headers=_headers(), timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        log.warning("Wiki pageviews недоступен (%s): %s", topic, exc)
        return TopicTrend(topic=topic, error="сеть недоступна")
    if r.status_code == 404:
        return TopicTrend(topic=topic, error="нет статьи/данных")
    if r.status_code != 200:
        return TopicTrend(topic=topic, error=f"HTTP {r.status_code}")
    series = parse_series(r.json())
    t = trend_from_series(series)
    if not t["ok"]:
        return TopicTrend(topic=topic, error=t.get("error", "нет данных"))
    return TopicTrend(topic=topic, ok=True, prior_avg=t["prior_avg"], recent_avg=t["recent_avg"],
                      growth=t["growth"], direction=t["direction"], spark=t["spark"])
