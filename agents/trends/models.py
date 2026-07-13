"""Модели трендов и темы по умолчанию."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

# Темы по умолчанию — названия статей ru.wikipedia (блюда, кухни, форматы).
# Несуществующие/без данных просто пропускаются.
DEFAULT_TOPICS = [
    "Пицца", "Суши", "Рамен", "Паста", "Хинкали", "Хачапури",
    "Тирамису", "Круассан", "Матча", "Комбуча", "Устрица", "Гамбургер",
]


@dataclass
class TopicTrend:
    topic: str
    ok: bool = False
    error: str = ""
    prior_avg: float = 0.0        # средние просмотры в первой половине окна
    recent_avg: float = 0.0       # во второй половине
    growth: float = 0.0           # прирост, %
    direction: str = "flat"       # up | down | flat
    spark: list[int] = field(default_factory=list)  # бакеты для мини-графика

    def to_dict(self) -> dict:
        return asdict(self)
