"""Парсер 2ГИС.

Два пути:
  1) Официальный 2GIS Catalog API (если задан DGIS_API_KEY) — стабильно.
  2) Best-effort парсинг публичной карточки фирмы (fallback) — 2ГИС активно
     защищается от ботов, поэтому при блокировке честно возвращаем ok=False.

Никогда не выдумываем рейтинг/отзывы: если данных нет — SourceSnapshot(ok=False).
"""
from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from config.settings import settings
from models.competitor import Competitor, Review, SourceSnapshot
from .http import get

log = logging.getLogger("restopulse.parser.dgis")

# Из ссылки вида https://2gis.ru/tyumen/firm/70000001234567890 достаём firm_id
_FIRM_ID_RE = re.compile(r"/firm/(\d+)")


def _extract_firm_id(url: str) -> str | None:
    m = _FIRM_ID_RE.search(url or "")
    return m.group(1) if m else None


def _fetch_via_api(firm_id: str) -> SourceSnapshot | None:
    """Стабильный путь через 2GIS Catalog API. Возвращает None, если ключа нет."""
    if not settings.dgis_api_key:
        return None
    snap = SourceSnapshot(source="dgis")
    url = "https://catalog.api.2gis.com/3.0/items/byid"
    resp = get(
        url,
        params={
            "id": firm_id,
            "key": settings.dgis_api_key,
            "fields": "items.reviews,items.rating",
        },
        respect_robots=False,
    )
    if resp is None:
        snap.error = "2GIS API недоступен"
        return snap
    try:
        item = resp.json()["result"]["items"][0]
    except (KeyError, IndexError, json.JSONDecodeError):
        snap.error = "2GIS API: неожиданный ответ"
        return snap
    reviews = item.get("reviews", {}) or {}
    snap.rating = reviews.get("general_rating") or item.get("rating")
    snap.reviews_count = reviews.get("general_review_count")
    snap.ok = snap.rating is not None or snap.reviews_count is not None
    if not snap.ok:
        snap.error = "2GIS API: рейтинг/отзывы отсутствуют"
    return snap


def _fetch_via_html(url: str) -> SourceSnapshot:
    """Fallback: пытаемся вытащить встроенный JSON состояния из HTML карточки.
    2ГИС часто отдаёт данные в window.initialState — если структура поменялась
    или пришла заглушка антибота, честно фиксируем ok=False."""
    snap = SourceSnapshot(source="dgis")
    resp = get(url)
    if resp is None:
        snap.error = "карточка 2ГИС недоступна (блокировка/сеть)"
        return snap

    html = resp.text
    # Пробуем найти рейтинг в JSON-LD (самый устойчивый вариант)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        agg = data.get("aggregateRating") if isinstance(data, dict) else None
        if agg:
            snap.rating = _to_float(agg.get("ratingValue"))
            snap.reviews_count = _to_int(agg.get("reviewCount") or agg.get("ratingCount"))
            snap.ok = snap.rating is not None
            if snap.ok:
                return snap

    snap.error = "не удалось разобрать карточку 2ГИС (возможно, антибот)"
    return snap


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _to_int(v) -> int | None:
    try:
        return int(re.sub(r"\D", "", str(v)))
    except (TypeError, ValueError):
        return None


def fetch(competitor: Competitor) -> SourceSnapshot:
    """Собирает метрики 2ГИС по конкуренту. Сначала API, затем HTML-fallback."""
    snap = SourceSnapshot(source="dgis")
    if not competitor.dgis_url:
        snap.error = "не задан dgis_url"
        return snap

    firm_id = _extract_firm_id(competitor.dgis_url)
    if firm_id:
        api_snap = _fetch_via_api(firm_id)
        if api_snap is not None and api_snap.ok:
            return api_snap

    return _fetch_via_html(competitor.dgis_url)
