"""Парсер Яндекс.Карт.

Два пути:
  1) Официальный Yandex Geosearch (Places) API (если задан YANDEX_API_KEY) —
     отдаёт рейтинг и число отзывов по org_id. Стабильно.
  2) Best-effort парсинг публичной карточки организации (fallback). Яндекс
     защищается от ботов, поэтому при блокировке возвращаем ok=False.

Второй источник нужен в первую очередь для сверки с 2ГИС.
"""
from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from config.settings import settings
from models.competitor import Competitor, SourceSnapshot
from .http import get

log = logging.getLogger("restopulse.parser.yandex")

GEOSEARCH_API = "https://search-maps.yandex.ru/v1/"


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


def _fetch_via_api(competitor: Competitor) -> SourceSnapshot | None:
    """Geosearch API. Ищем организацию по названию+адресу, берём рейтинг из
    properties.CompanyMetaData/ScoreData. None — если нет ключа."""
    if not settings.yandex_api_key:
        return None
    snap = SourceSnapshot(source="yandex")
    query = f"{competitor.name} {competitor.address}".strip()
    resp = get(
        GEOSEARCH_API,
        params={
            "apikey": settings.yandex_api_key,
            "text": query,
            "type": "biz",
            "lang": "ru_RU",
            "results": 1,
        },
        respect_robots=False,
    )
    if resp is None:
        snap.error = "Yandex API недоступен"
        return snap
    try:
        features = resp.json().get("features", [])
    except json.JSONDecodeError:
        snap.error = "Yandex API: неожиданный ответ"
        return snap
    if not features:
        snap.error = "Yandex API: организация не найдена"
        return snap
    props = features[0].get("properties", {})
    meta = props.get("CompanyMetaData", {})
    score = meta.get("score") or meta.get("ScoreData", {}).get("ratingValue")
    reviews = meta.get("ratings") or meta.get("ScoreData", {}).get("reviewCount")
    snap.rating = _to_float(score)
    snap.reviews_count = _to_int(reviews)
    snap.ok = snap.rating is not None or snap.reviews_count is not None
    if not snap.ok:
        snap.error = "Yandex API: рейтинг отсутствует в ответе"
    return snap


def _fetch_via_html(url: str) -> SourceSnapshot:
    """Fallback: JSON-LD aggregateRating из HTML карточки Яндекс.Карт."""
    snap = SourceSnapshot(source="yandex")
    resp = get(url)
    if resp is None:
        snap.error = "карточка Яндекс.Карт недоступна (блокировка/сеть)"
        return snap

    soup = BeautifulSoup(resp.text, "html.parser")
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

    snap.error = "не удалось разобрать карточку Яндекс.Карт (возможно, антибот)"
    return snap


def fetch(competitor: Competitor) -> SourceSnapshot:
    """Собирает метрики Яндекс.Карт по конкуренту. Сначала API, затем HTML."""
    api_snap = _fetch_via_api(competitor)
    if api_snap is not None and api_snap.ok:
        return api_snap

    if competitor.yandex_url:
        return _fetch_via_html(competitor.yandex_url)

    snap = SourceSnapshot(source="yandex")
    snap.error = api_snap.error if api_snap else "не задан yandex_url и нет YANDEX_API_KEY"
    return snap
