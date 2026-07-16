"""Сервис «Программа заведения»: ДНК + генерация концептов для UI."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from . import calendar as cal
from . import campaign as camp
from . import engine
from .models import VenueDNA, EventConcept

log = logging.getLogger("restopulse.programming")

# Тренды тянутся из Wikipedia последовательно и занимают десятки секунд —
# держим результат в кэше, чтобы страница не ждала на каждый сбор программы.
TRENDS_TTL_SEC = 6 * 3600
_trends_cache: dict = {"value": [], "exp": 0.0}

MONTHS_RU = ["", "январь", "февраль", "март", "апрель", "май", "июнь", "июль",
             "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


# ── ДНК ───────────────────────────────────────────────────────────────
def get_dna() -> VenueDNA:
    from config.store import store
    return VenueDNA.from_dict(store.get_venue())


def save_dna(patch: dict) -> VenueDNA:
    from config.store import store
    store.update_venue(patch or {})
    return get_dna()


# ── Тренды и разведка (best-effort, не мешают генерации) ───────────────
def _trend_lines(*, force: bool = False) -> list[str]:
    """Растущие темы. Кэш на TTL: сбор трендов идёт десятки секунд.

    force=False возвращает только тёплый кэш (мгновенно, без сети).
    """
    now = time.time()
    if _trends_cache["exp"] > now:
        return list(_trends_cache["value"])
    if not force:
        return []
    try:
        from agents.trends.service import analyze
        data = analyze()
        lines = [f"{r['topic']} (+{r['growth']}%)" for r in data.get("rising", [])[:5]]
    except Exception as exc:
        log.debug("Тренды недоступны: %s", exc)
        return []
    _trends_cache["value"] = lines
    _trends_cache["exp"] = now + TRENDS_TTL_SEC
    return list(lines)


def _competitor_obs() -> list[dict]:
    try:
        from agents.content.ideas import _observations_from_repo
        return _observations_from_repo()
    except Exception as exc:
        log.debug("Наблюдения по конкурентам недоступны: %s", exc)
        return []


# ── Программа ─────────────────────────────────────────────────────────
def programma(*, year: int | None = None, month: int | None = None, n: int = 5,
              use_llm: bool = True, with_trends: bool = False) -> dict:
    """with_trends=True разрешает медленный сбор трендов (иначе — только тёплый кэш)."""
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month
    dna = get_dna()
    # Программа смотрит вперёд: прошедшие поводы текущего месяца — шум
    today_iso = now.date().isoformat()
    occasions = [o for o in cal.occasions_for(year, month) if o.date >= today_iso]
    trends = _trend_lines(force=with_trends)
    obs = _competitor_obs()
    concepts, mode = engine.generate(
        dna, occasions, n=n, trends=trends, competitor_obs=obs, use_llm=use_llm)
    return {
        "year": year, "month": month, "month_name": MONTHS_RU[month],
        "mode": mode,
        "dna": dna.to_dict(),
        "occasions": [o.to_dict() for o in occasions],
        "trends": trends,
        "concepts": [c.to_dict() for c in concepts],
        "notice": ("" if occasions else
                   "В этом месяце поводы уже прошли — выберите следующий месяц."),
    }


# ── Кампания из концепта ──────────────────────────────────────────────
def campaign(concept_data: dict, *, networks: list[str] | None = None,
             use_llm: bool = True, save: bool = False) -> dict:
    """Строит серию постов под концепт. save=True — кладёт черновиками в очередь."""
    known = set(EventConcept.__dataclass_fields__)
    concept = EventConcept(**{k: v for k, v in (concept_data or {}).items() if k in known})
    if not concept.date:
        raise ValueError("У концепта нет даты — кампанию не построить")
    dna = get_dna()
    beats, mode = camp.build(concept, dna, networks=networks, use_llm=use_llm)
    out = {"mode": mode, "concept": concept.title, "date": concept.date,
           "beats": [b.to_dict() for b in beats]}
    if save:
        out["saved"] = camp.save_as_drafts(beats)
    return out
