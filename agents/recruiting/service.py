"""Сервис рекрутинга: анализ рынка труда по ролям + кто активно нанимает."""
from __future__ import annotations

import logging
import time
from collections import Counter

from . import hh
from .models import DEFAULT_ROLES

log = logging.getLogger("restopulse.recruiting")

REQUEST_PAUSE = 0.3  # вежливая пауза между запросами к HH


def market(city: str = "Тюмень", roles: list[str] | None = None) -> dict:
    """Анализ рынка труда: по каждой роли — вакансии, зарплата, топ-работодатели.
    Плюс агрегат «кто активно нанимает» по всем ролям."""
    roles = [r.strip() for r in (roles or DEFAULT_ROLES) if r.strip()]
    area = hh.suggest_area(city)

    reports = []
    hiring = Counter()
    statuses = set()
    for i, role in enumerate(roles):
        if i:
            time.sleep(REQUEST_PAUSE)
        found, vacs, status = hh.fetch_vacancies(role, area)
        statuses.add(status)
        rm = hh.role_market(role, vacs, found)
        reports.append(rm.to_dict())
        for emp in rm.top_employers:
            hiring[emp["name"]] += emp["count"]

    hiring_top = [{"name": n, "count": c} for n, c in hiring.most_common(8)]

    return {
        "city": city,
        "area_id": area,
        "area_resolved": bool(area),
        "blocked": ("forbidden" in statuses and "ok" not in statuses),
        "roles": reports,
        "hiring": hiring_top,
        "notice": _notice(area, reports, statuses),
    }


def _notice(area: str | None, reports: list[dict], statuses: set) -> str:
    if "forbidden" in statuses and "ok" not in statuses:
        return ("HeadHunter закрыл анонимный поиск вакансий (ответ 403). Зарегистрируйте "
                "бесплатное приложение на dev.hh.ru и задайте HH_CLIENT_ID и HH_CLIENT_SECRET "
                "в .env — после этого рынок будет анализироваться. На собственном сервере "
                "доступ часто открыт и без ключей.")
    if not area:
        return ("Не удалось определить регион на HH — показаны данные по всей России. "
                "Уточните город.")
    total = sum(r["found"] for r in reports)
    if total == 0:
        return "По заданным ролям вакансий не найдено. Проверьте формулировки ролей."
    return "Данные HeadHunter (публичные вакансии). Зарплаты — на руки, ориентировочно."


def default_roles() -> list[str]:
    return list(DEFAULT_ROLES)
