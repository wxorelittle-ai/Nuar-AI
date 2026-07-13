"""Оркестратор мгновенного анализа при онбординге.

analyze() = discovery (реальный или демо) → стратегия → единый dict для UI.
"""
from __future__ import annotations

import logging

from config.settings import settings
from .models import RestaurantProfile, NearbyCompetitor, SEGMENTS
from . import discovery, demo_data
from .strategy import build_strategy
from .voice import maitre_note

log = logging.getLogger("restopulse.analyzer.service")


def analyze(name: str, address: str = "", city: str = "Тюмень",
            segment: str = "restaurant", *, allow_demo: bool = True) -> dict:
    """Полный анализ заведения. Возвращает dict, готовый к отдаче в JSON.

    Источник данных:
      • YANDEX_API_KEY задан → реальный discovery;
      • ключа нет и allow_demo → демо-данные (помечены demo=true);
      • ключа нет и не allow_demo → пустое окружение, стратегия по профилю.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Не указано название ресторана")
    if segment not in SEGMENTS:
        segment = "restaurant"

    demo = False
    result = discovery.discover(name, address, city, segment)
    if result is not None:
        profile, competitors = result
        source = "yandex_api"
    elif allow_demo:
        profile = demo_data.demo_profile(name, address, city, segment)
        competitors = demo_data.demo_competitors()
        demo = True
        source = "demo"
    else:
        profile = RestaurantProfile(name=name, address=address, city=city, segment=segment)
        competitors = []
        source = "empty"

    strategy = build_strategy(profile, competitors)

    return {
        "demo": demo,
        "source": source,
        "profile": profile.to_dict(),
        "competitors": [c.to_dict() for c in competitors],
        "strategy": strategy.to_dict(),
        "maitre": maitre_note(profile, strategy),
        "notice": _notice(source),
    }


def _notice(source: str) -> str:
    if source == "demo":
        return ("Показаны демонстрационные данные по округу (иллюстрация на конкурентной карте Тюмени). "
                "Добавьте YANDEX_API_KEY в .env — и анализ пойдёт по реальным данным.")
    if source == "empty":
        return "Реальные данные округа недоступны (нет YANDEX_API_KEY). Стратегия построена по профилю заведения."
    return "Данные округа получены через Yandex Geosearch API."
