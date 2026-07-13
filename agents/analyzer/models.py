"""Модели данных для мгновенного анализа (онбординг).

Отдельно от models/competitor.py (там — недельные снимки для дайджеста).
Здесь — «фотография» ресторана и его окружения на момент онбординга.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


# Сегменты заведения — влияют на позиционирование и контент-линии
SEGMENTS = {
    "fine_dining": "Fine dining / премиум",
    "restaurant": "Ресторан",
    "bar": "Бар / гастропаб",
    "cafe": "Кафе / кофейня",
    "fast": "Фастфуд / стрит-фуд",
}


@dataclass
class PlatformStats:
    """Метрики заведения на одной площадке (2ГИС / Яндекс)."""

    platform: str                 # "2ГИС" | "Яндекс.Карты"
    rating: float | None = None
    reviews_count: int | None = None
    ok: bool = False              # есть ли данные с площадки
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RestaurantProfile:
    """Профиль анализируемого ресторана."""

    name: str
    address: str = ""
    city: str = "Тюмень"
    segment: str = "restaurant"
    lat: float | None = None
    lon: float | None = None
    platforms: list[PlatformStats] = field(default_factory=list)

    @property
    def best_rating(self) -> float | None:
        vals = [p.rating for p in self.platforms if p.ok and p.rating is not None]
        return max(vals) if vals else None

    @property
    def total_reviews(self) -> int:
        return sum(p.reviews_count or 0 for p in self.platforms if p.ok)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["segment_label"] = SEGMENTS.get(self.segment, self.segment)
        d["best_rating"] = self.best_rating
        d["total_reviews"] = self.total_reviews
        return d


@dataclass
class NearbyCompetitor:
    """Конкурент, найденный в округе."""

    name: str
    address: str = ""
    rating: float | None = None
    reviews_count: int | None = None
    distance_m: int | None = None
    categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SwotItem:
    text: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Priority:
    """Приоритетное действие (quick win)."""

    title: str
    why: str
    effort: str = "средний"       # низкий | средний | высокий
    impact: str = "средний"       # низкий | средний | высокий
    weight: int = 0               # для сортировки

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("weight", None)
        return d


@dataclass
class ContentLine:
    title: str
    desc: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Strategy:
    """Результат стратегического анализа."""

    positioning: str = ""
    your_rating: float | None = None
    avg_competitor_rating: float | None = None
    rank: int | None = None
    total_places: int | None = None
    strengths: list[SwotItem] = field(default_factory=list)
    weaknesses: list[SwotItem] = field(default_factory=list)
    opportunities: list[SwotItem] = field(default_factory=list)
    threats: list[SwotItem] = field(default_factory=list)
    priorities: list[Priority] = field(default_factory=list)
    content_lines: list[ContentLine] = field(default_factory=list)
    top_threats: list[NearbyCompetitor] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "positioning": self.positioning,
            "your_rating": self.your_rating,
            "avg_competitor_rating": self.avg_competitor_rating,
            "rank": self.rank,
            "total_places": self.total_places,
            "swot": {
                "strengths": [s.to_dict() for s in self.strengths],
                "weaknesses": [s.to_dict() for s in self.weaknesses],
                "opportunities": [s.to_dict() for s in self.opportunities],
                "threats": [s.to_dict() for s in self.threats],
            },
            "priorities": [p.to_dict() for p in self.priorities],
            "content_lines": [c.to_dict() for c in self.content_lines],
            "top_threats": [t.to_dict() for t in self.top_threats],
        }
