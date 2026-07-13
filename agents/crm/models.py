"""Модели CRM: гость и сегменты."""
from __future__ import annotations

from dataclasses import dataclass, asdict

# Сегменты гостей
VIP = "vip"
REGULAR = "regular"
CORPORATE = "corporate"
POTENTIAL = "potential"
OCCASIONAL = "occasional"
SEGMENTS = {
    VIP: "VIP-постоянные",
    REGULAR: "Постоянные",
    CORPORATE: "Корпоративные",
    POTENTIAL: "Разовые с потенциалом",
    OCCASIONAL: "Разовые",
}


@dataclass
class Guest:
    id: str
    name: str = ""
    phone: str = ""
    email: str = ""
    birthday: str = ""        # "MM-DD" (или пусто)
    last_visit: str = ""      # ISO-дата "YYYY-MM-DD" (или пусто)
    visits: int = 0
    avg_check: int = 0        # средний чек, ₽
    tags: str = ""
    segment: str = OCCASIONAL
    created_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["segment_label"] = SEGMENTS.get(self.segment, self.segment)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Guest":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
