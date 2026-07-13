"""Модели рекрутинга и роли по умолчанию."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

# Типовые роли ресторана для анализа рынка
DEFAULT_ROLES = [
    "Официант",
    "Повар",
    "Бармен",
    "Хостес",
    "Администратор ресторана",
    "Шеф-повар",
]


@dataclass
class Vacancy:
    name: str = ""
    employer: str = ""
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str | None = None      # RUR, USD…
    gross: bool | None = None        # True = до вычета НДФЛ
    area: str = ""
    url: str = ""
    published_at: str = ""


@dataclass
class RoleMarket:
    """Срез рынка по одной роли."""

    role: str
    found: int = 0                   # всего вакансий на HH
    with_salary: int = 0             # из выборки — с указанной зарплатой
    salary_median: int | None = None # на руки, ориентировочно (RUR)
    salary_p25: int | None = None
    salary_p75: int | None = None
    top_employers: list[dict] = field(default_factory=list)  # [{name, count}]

    def to_dict(self) -> dict:
        return asdict(self)
