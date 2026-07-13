"""Модели данных по конкуренту и снимку его метрик.

Используем dataclass'ы (без ORM) — модуль должен запускаться и на голом
JSON-файле, и на PostgreSQL. Сериализация в dict/из dict — вручную,
чтобы одинаково класть и в JSON, и в БД.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Competitor:
    """Один конкурент из config/competitors.yaml."""

    name: str
    address: str = ""
    priority: str = "medium"  # high | medium | low
    monitor_frequency: str = "weekly"
    dgis_url: str = ""
    yandex_url: str = ""
    yandex_org_id: str = ""
    vk_domain: str = ""
    note: str = ""

    @classmethod
    def from_config(cls, raw: dict) -> "Competitor":
        """Создаёт объект из записи YAML, игнорируя лишние поля."""
        known = {f for f in cls.__dataclass_fields__}
        # yandex_org_id/числа в YAML могут прийти int — приводим к строке
        cleaned = {}
        for k, v in raw.items():
            if k not in known:
                continue
            cleaned[k] = "" if v is None else (str(v) if k.endswith("_id") else v)
        return cls(**cleaned)


@dataclass
class Review:
    """Один отзыв (2ГИС/Яндекс). Текст храним усечённым."""

    author: str = ""
    rating: float | None = None
    text: str = ""
    date: str = ""  # ISO-строка, как отдал источник

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Review":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class SourceSnapshot:
    """Снимок метрик по ОДНОМУ источнику (2ГИС / Яндекс / VK) на момент сбора."""

    source: str  # "dgis" | "yandex" | "vk"
    ok: bool = False  # удалось ли собрать; False = источник недоступен/заблокирован
    error: str = ""  # причина, если ok=False

    rating: float | None = None
    reviews_count: int | None = None
    recent_reviews: list[Review] = field(default_factory=list)

    # VK-специфика
    subscribers: int | None = None
    posts_last_week: int | None = None
    latest_post_text: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["recent_reviews"] = [r.to_dict() for r in self.recent_reviews]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SourceSnapshot":
        reviews = [Review.from_dict(r) for r in d.get("recent_reviews", [])]
        fields = {k: d.get(k) for k in cls.__dataclass_fields__ if k != "recent_reviews"}
        obj = cls(**fields)
        obj.recent_reviews = reviews
        return obj


@dataclass
class CompetitorSnapshot:
    """Полный снимок по конкуренту за неделю: все источники + СМИ-упоминания."""

    competitor_name: str
    collected_at: str  # ISO-время сбора (передаётся снаружи — в скрипте нет Date.now-табу, но держим единообразно)
    sources: dict[str, SourceSnapshot] = field(default_factory=dict)
    media_mentions: list[dict] = field(default_factory=list)  # [{source, title, url}]

    def to_dict(self) -> dict:
        return {
            "competitor_name": self.competitor_name,
            "collected_at": self.collected_at,
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "media_mentions": self.media_mentions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CompetitorSnapshot":
        sources = {k: SourceSnapshot.from_dict(v) for k, v in d.get("sources", {}).items()}
        return cls(
            competitor_name=d["competitor_name"],
            collected_at=d.get("collected_at", ""),
            sources=sources,
            media_mentions=d.get("media_mentions", []),
        )
