"""Поиск ресторана и конкурентов в округе.

Использует официальный Yandex Geosearch (Places) API, когда задан
YANDEX_API_KEY. Без ключа честно возвращает пусто (см. service.py — там
включается демо-режим по явному флагу, помеченный как демонстрационный).

Ratings в Geosearch API приходят не всегда — где их нет, ставим None, а не
выдумываем. Дистанции считаем по гаверсинусу от координат заведения.
"""
from __future__ import annotations

import logging
import math

from config.settings import settings
from agents.competitor_scraper.parsers.http import get
from .models import RestaurantProfile, NearbyCompetitor, PlatformStats

log = logging.getLogger("restopulse.analyzer.discovery")

GEOSEARCH_API = "https://search-maps.yandex.ru/v1/"


def haversine_m(lat1, lon1, lat2, lon2) -> int:
    """Расстояние между точками в метрах."""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))


def _biz(feature: dict) -> dict:
    return feature.get("properties", {}).get("CompanyMetaData", {})


def _rating_from(meta: dict) -> tuple[float | None, int | None]:
    """Пытается достать рейтинг/число отзывов, если API их вернул."""
    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _i(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    score = meta.get("score")
    reviews = meta.get("ratings") or meta.get("reviews")
    sd = meta.get("ScoreData") or {}
    return _f(score if score is not None else sd.get("ratingValue")), _i(
        reviews if reviews is not None else sd.get("reviewCount"))


def _search(text: str, *, results: int = 1, ll: str | None = None, spn: str | None = None) -> list[dict]:
    params = {
        "apikey": settings.yandex_api_key,
        "text": text,
        "type": "biz",
        "lang": "ru_RU",
        "results": results,
    }
    if ll:
        params["ll"] = ll
    if spn:
        params["spn"] = spn
    resp = get(GEOSEARCH_API, params=params, respect_robots=False)
    if resp is None:
        return []
    try:
        return resp.json().get("features", [])
    except ValueError:
        return []


def discover(name: str, address: str, city: str, segment: str) -> tuple[RestaurantProfile, list[NearbyCompetitor]] | None:
    """Находит заведение и конкурентов рядом через Yandex API.
    Возвращает None, если ключа нет (тогда вызывающий включит демо-режим)."""
    if not settings.yandex_api_key:
        return None

    profile = RestaurantProfile(name=name, address=address, city=city, segment=segment)

    # 1) Само заведение
    self_feats = _search(f"{name} {address} {city}".strip(), results=1)
    if self_feats:
        f = self_feats[0]
        lon, lat = (f.get("geometry", {}).get("coordinates") or [None, None])[:2]
        profile.lat, profile.lon = lat, lon
        meta = _biz(f)
        rating, reviews = _rating_from(meta)
        profile.platforms.append(PlatformStats(
            platform="Яндекс.Карты", rating=rating, reviews_count=reviews,
            ok=(rating is not None or reviews is not None),
            url=meta.get("url", "")))

    competitors: list[NearbyCompetitor] = []
    if profile.lat and profile.lon:
        ll = f"{profile.lon},{profile.lat}"
        # ~1.2 км окно вокруг заведения
        feats = _search("ресторан", results=15, ll=ll, spn="0.02,0.02")
        for f in feats:
            meta = _biz(f)
            cname = meta.get("name", "")
            if not cname or cname.lower() == name.lower():
                continue
            lon, lat = (f.get("geometry", {}).get("coordinates") or [None, None])[:2]
            dist = haversine_m(profile.lat, profile.lon, lat, lon) if lat and lon else None
            rating, reviews = _rating_from(meta)
            cats = [c.get("name", "") for c in meta.get("Categories", [])]
            competitors.append(NearbyCompetitor(
                name=cname, address=meta.get("address", ""),
                rating=rating, reviews_count=reviews,
                distance_m=dist, categories=cats))
        competitors.sort(key=lambda c: c.distance_m or 10**9)

    return profile, competitors
