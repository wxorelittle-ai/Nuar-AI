"""Демонстрационные данные для онбординга без API-ключа.

ВНИМАНИЕ: это иллюстративный набор для показа работы интерфейса. Он собран из
публичной конкурентной карты Тюмени (проектный контекст Nuar) и НЕ является
результатом реального сбора. В ответе API помечается флагом demo=true, чтобы
на экране было видно: данные демонстрационные. В проде с YANDEX_API_KEY
включается реальный discovery.
"""
from __future__ import annotations

from .models import RestaurantProfile, NearbyCompetitor, PlatformStats


def demo_profile(name: str, address: str, city: str, segment: str) -> RestaurantProfile:
    """Профиль на основе введённых данных + иллюстративные метрики площадок.

    Метрики намеренно повторяют известный кейс Nuar (высокий 2ГИС, дыра на
    Яндексе), чтобы показать, как система подсвечивает проблему."""
    p = RestaurantProfile(name=name, address=address or "Советская, 20", city=city, segment=segment)
    p.lat, p.lon = 57.1530, 65.5343  # центр Тюмени (иллюстративно)
    p.platforms = [
        PlatformStats(platform="2ГИС", rating=4.8, reviews_count=98, ok=True),
        PlatformStats(platform="Яндекс.Карты", rating=4.1, reviews_count=3, ok=True),
    ]
    return p


def demo_competitors() -> list[NearbyCompetitor]:
    """Иллюстративные конкуренты рядом (конкурентная карта Тюмени)."""
    return [
        NearbyCompetitor("Арбат", "Советская, 21", rating=4.8, reviews_count=210,
                         distance_m=80, categories=["Ресторан", "Бар"]),
        NearbyCompetitor("Мята", "Советская, 20", rating=4.4, reviews_count=64,
                         distance_m=30, categories=["Ресторан"]),
        NearbyCompetitor("Сыроварня", "Советская, 54", rating=4.5, reviews_count=180,
                         distance_m=520, categories=["Ресторан"]),
        NearbyCompetitor("Ресторан-музей", "Володарского, 3", rating=4.6, reviews_count=140,
                         distance_m=900, categories=["Ресторан"]),
        NearbyCompetitor("MaxiMilian", "Тюмень, центр", rating=4.2, reviews_count=95,
                         distance_m=1100, categories=["Итальянская кухня"]),
        NearbyCompetitor("Nori", "Тюмень, центр", rating=4.3, reviews_count=120,
                         distance_m=1300, categories=["Паназия"]),
    ]
