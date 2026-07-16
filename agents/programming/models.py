"""Модели «Программы заведения»: ДНК-профиль и концепт события.

ДНК — постоянный портрет заведения (концепция, аудитория, что заходит, стоп-темы),
который кормит идейный движок. Концепт — конкретный вечер/коллаборация с датой,
механикой, партнёром, KPI и готовым мини-анонсом.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class VenueDNA:
    """ДНК заведения — фундамент для генерации идей."""

    name: str = "Nuar"
    city: str = "Тюмень"
    concept: str = "нуар/джаз-бар с авторскими коктейлями, вечерний формат"
    segment: str = "bar"                       # см. analyzer.models.SEGMENTS
    avg_check: int = 2500                      # средний чек, ₽
    capacity: int = 60                         # посадка
    audience: str = "25–40 лет, ценят атмосферу и вкус, ходят вечером и по выходным"
    # что уже заходит — усиливать; стоп-темы — не предлагать
    works_well: list[str] = field(default_factory=lambda: [
        "живая музыка", "авторские коктейли", "тёмная камерная атмосфера"])
    avoid: list[str] = field(default_factory=lambda: [
        "детские праздники", "дневной фастфуд", "громкий поп-формат"])
    # типы локальных партнёров для коллабораций
    partner_types: list[str] = field(default_factory=lambda: [
        "джаз/блюз-музыканты", "локальная винокурня/крафт", "книжный магазин/клуб",
        "киноклуб", "арт-галерея/фотографы", "обжарщики кофе", "парфюмерная мастерская"])
    tone: str = "сдержанный, с холодком старой школы, без эмодзи и восклицаний"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "VenueDNA":
        d = d or {}
        base = cls()
        for k in base.to_dict():
            if k in d and d[k] not in (None, ""):
                setattr(base, k, d[k])
        return base

    def brief(self) -> str:
        """Короткое текстовое ДНК для промпта LLM."""
        return (
            f"Заведение: «{self.name}», {self.city}. Концепция: {self.concept}. "
            f"Сегмент: {self.segment}, средний чек ~{self.avg_check} ₽, посадка {self.capacity}. "
            f"Аудитория: {self.audience}. "
            f"Заходит: {', '.join(self.works_well)}. "
            f"Не предлагать: {', '.join(self.avoid)}. "
            f"Партнёры для коллабораций: {', '.join(self.partner_types)}. "
            f"Тон: {self.tone}."
        )


@dataclass
class EventConcept:
    """Концепт вечера или коллаборации — то, что видит управляющий."""

    title: str                                 # название вечера
    date: str = ""                             # ISO-дата (YYYY-MM-DD) или ""
    weekday: str = ""                          # «пт», «сб» …
    occasion: str = ""                         # повод/триггер
    kind: str = "event"                        # event | collab
    pitch: str = ""                            # суть в 1–2 фразах
    mechanics: list[str] = field(default_factory=list)   # механика вечера
    collab: str = ""                           # кто партнёр и зачем
    differentiation: str = ""                  # чего не делают конкуренты
    kpi: str = ""                              # как измерим успех
    risk: str = ""                             # риск и как снять
    teaser: str = ""                           # готовый мини-анонс (голос бренда)
    tags: list[str] = field(default_factory=list)
    source: str = "template"                   # template | llm

    def to_dict(self) -> dict:
        return asdict(self)
