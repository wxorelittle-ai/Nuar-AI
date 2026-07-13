"""Модели анализа соцсетей."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class PostStat:
    id: str = ""
    owner_id: int = 0
    text: str = ""
    likes: int = 0
    comments: int = 0
    views: int = 0
    date: int = 0            # unix ts (UTC)

    @property
    def link(self) -> str:
        return f"https://vk.com/wall{self.owner_id}_{self.id}" if self.id else ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["link"] = self.link
        d["text"] = self.text[:160]
        return d


@dataclass
class VKAnalytics:
    domain: str
    ok: bool = False
    error: str = ""

    subscribers: int | None = None
    posts_analyzed: int = 0
    span_days: float = 0.0
    posts_per_week: float = 0.0

    avg_likes: float = 0.0
    avg_comments: float = 0.0
    avg_views: float = 0.0
    engagement_rate: float = 0.0   # avg_likes / avg_views, %

    best_weekday: str = ""
    by_weekday: list[int] = field(default_factory=lambda: [0] * 7)  # Пн..Вс
    top_words: list[dict] = field(default_factory=list)            # [{word, count}]
    top_posts: list[dict] = field(default_factory=list)            # PostStat.to_dict

    def to_dict(self) -> dict:
        return asdict(self)
