"""Модель дайджеста: результат сравнения двух недельных срезов.

Digest собирается из списка изменений (DigestChange) по всем конкурентам и
рендерится в Telegram Markdown в agents/competitor_scraper/digest.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Категории изменений — определяют, в какой раздел дайджеста попадёт строка.
IMPORTANT = "important"       # 🔴 ВАЖНО: события, акции, анонсы
RATING = "rating"             # 📈 изменения рейтингов
VK_ACTIVITY = "vk_activity"   # 📱 активность в VK
MEDIA = "media"               # 📰 упоминания в СМИ


@dataclass
class DigestChange:
    """Одно замеченное изменение по конкуренту."""

    competitor_name: str
    category: str          # одна из констант выше
    text: str              # готовая строка для дайджеста (без маркера •)
    weight: int = 0        # приоритет внутри раздела (больше = выше)


@dataclass
class Digest:
    """Собранный недельный дайджест."""

    week_label: str                       # человекочитаемая метка недели
    changes: list[DigestChange] = field(default_factory=list)
    recommendation: str = ""              # итоговая рекомендация управляющему
    sources_ok: int = 0                   # сколько источников успешно собрано
    sources_failed: int = 0               # сколько источников не удалось собрать

    def by_category(self, category: str) -> list[DigestChange]:
        items = [c for c in self.changes if c.category == category]
        return sorted(items, key=lambda c: c.weight, reverse=True)

    @property
    def is_empty(self) -> bool:
        return not self.changes
