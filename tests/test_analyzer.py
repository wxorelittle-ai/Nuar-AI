"""Тесты стратегического движка и сервиса анализа (без сети)."""
from __future__ import annotations

from agents.analyzer.models import RestaurantProfile, NearbyCompetitor, PlatformStats
from agents.analyzer.strategy import build_strategy
from agents.analyzer.service import analyze


def _profile(seg="fine_dining", y_rating=4.1, y_reviews=3, d_rating=4.8, d_reviews=98):
    p = RestaurantProfile(name="Nuar", address="Советская, 20", segment=seg)
    p.platforms = [
        PlatformStats(platform="2ГИС", rating=d_rating, reviews_count=d_reviews, ok=True),
        PlatformStats(platform="Яндекс.Карты", rating=y_rating, reviews_count=y_reviews, ok=True),
    ]
    return p


def test_review_gap_detected():
    # 2ГИС 98 отзывов vs Яндекс 3 → дыра на Яндексе
    p = _profile()
    s = build_strategy(p, [])
    assert any("Яндекс" in w.text and "дыра" in w.text.lower() for w in s.weaknesses)


def test_priority_closes_gap_first():
    p = _profile()
    s = build_strategy(p, [])
    assert s.priorities, "должны быть приоритеты"
    assert "Яндекс" in s.priorities[0].title  # закрытие дыры — первый приоритет


def test_market_position_rank():
    p = _profile(d_rating=4.8)
    comps = [
        NearbyCompetitor("Арбат", rating=4.8, distance_m=80),
        NearbyCompetitor("Мята", rating=4.4, distance_m=30),
    ]
    s = build_strategy(p, comps)
    assert s.avg_competitor_rating == 4.6
    assert s.total_places == 3
    assert s.rank in (1, 2)  # ваш 4.8 делит верх с Арбатом


def test_nearby_strong_competitor_is_threat():
    p = _profile(d_rating=4.5)
    comps = [NearbyCompetitor("Арбат", rating=4.8, distance_m=80)]
    s = build_strategy(p, comps)
    assert any(t.name == "Арбат" for t in s.top_threats)


def test_fine_dining_has_vip_priority_and_music_content():
    p = _profile(seg="fine_dining")
    s = build_strategy(p, [])
    assert any("VIP" in pr.title for pr in s.priorities)
    assert any("музык" in cl.title.lower() for cl in s.content_lines)


def test_missing_platform_flagged():
    p = RestaurantProfile(name="X", segment="restaurant")
    p.platforms = [
        PlatformStats(platform="2ГИС", rating=4.5, reviews_count=40, ok=True),
        PlatformStats(platform="Яндекс.Карты", ok=False),
    ]
    s = build_strategy(p, [])
    assert any("Яндекс" in w.text for w in s.weaknesses)


def test_analyze_demo_mode_returns_full_payload():
    # Без YANDEX_API_KEY сервис отдаёт демо-данные, помеченные demo=true
    data = analyze("Nuar", "Советская, 20", "Тюмень", "fine_dining")
    assert data["demo"] is True
    assert data["profile"]["name"] == "Nuar"
    assert len(data["competitors"]) > 0
    assert data["strategy"]["priorities"]
    assert data["strategy"]["swot"]["weaknesses"]
    assert "демонстрац" in data["notice"].lower()


def test_analyze_requires_name():
    import pytest
    with pytest.raises(ValueError):
        analyze("")
