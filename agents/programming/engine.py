"""Идейный движок: поводы + ДНК (+ тренды, + разведка) → концепты вечеров.

Два пути:
  • template_concepts — детерминированная сборка из повода и ДНК (без сети,
    полностью тестируется, работает без ключей);
  • llm_concepts — та же входная картина отдаётся LLM в голосе МЭТРА, ответ
    (JSON) разбирается; при любой осечке — откат на шаблон.
"""
from __future__ import annotations

import json
import logging

from .models import VenueDNA, EventConcept
from .calendar import Occasion

log = logging.getLogger("restopulse.programming.engine")

# Какой тип партнёра уместен под тип повода
_PARTNER_BY_KIND = {
    "music": ["джаз/блюз-музыканты"],
    "cinema": ["киноклуб", "арт-галерея/фотографы"],
    "bar": ["локальная винокурня/крафт", "обжарщики кофе"],
    "cultural": ["книжный магазин/клуб", "киноклуб", "арт-галерея/фотографы"],
    "civic": ["джаз/блюз-музыканты", "локальная винокурня/крафт"],
    "seasonal": ["джаз/блюз-музыканты", "арт-галерея/фотографы"],
}


def _partner_for(kind: str, dna: VenueDNA) -> str:
    wanted = _PARTNER_BY_KIND.get(kind, [])
    for w in wanted:
        if w in dna.partner_types:
            return w
    return dna.partner_types[0] if dna.partner_types else "локальный партнёр"


def _kpi_for(occ: Occasion) -> str:
    if occ.weekday in ("пт", "сб"):
        return "заполняемость зала в прайм + средний чек выше обычного вечера"
    return "трафик в будний вечер (обычно слабый) + новые гости с афиши"


def _template_concept(occ: Occasion, dna: VenueDNA, competitor_hint: str = "") -> EventConcept:
    partner = _partner_for(occ.kind, dna)
    kind = "collab"
    mechanics = [occ.fit] if occ.fit else []
    if occ.kind == "music":
        mechanics += ["живой сет приглашённого состава", "коктейль вечера под тему"]
    elif occ.kind in ("cultural", "cinema"):
        mechanics += ["сюжет/сценарий вечера", "тематическое коктейль-меню", "приглушённый свет и дресс-код"]
    elif occ.kind == "bar":
        mechanics += ["дегустация/спецкарта", "шоу за стойкой"]
    else:
        mechanics += ["тематическая подача", "живая музыка фоном"]

    diff = competitor_hint or "у конкурентов обычно «просто живая музыка» без сюжета — вы заходите форматом"
    risk = ("тематика нишевая — тизерить заранее и объяснять формат"
            if not occ.festive or occ.kind in ("cinema", "cultural")
            else "стандартный риск низкой явки в будни — усилить анонсом")
    teaser = f"{occ.date} · «{dna.name}» приглашает на вечер по случаю «{occ.title}». Подробности скоро."

    return EventConcept(
        title=f"{occ.title}: вечер в «{dna.name}»",
        date=occ.date, weekday=occ.weekday, occasion=occ.title,
        kind=kind, pitch=f"{occ.note}. {occ.fit}".strip(". "),
        mechanics=[m for m in mechanics if m],
        collab=f"{partner} — общая аудитория и совместный анонс",
        differentiation=diff, kpi=_kpi_for(occ),
        risk=risk, teaser=teaser,
        tags=[occ.kind, occ.title], source="template",
    )


def _rank(occasions: list[Occasion]) -> list[Occasion]:
    """Приоритет: профильные (музыка/бар/культура/кино) и festive — выше."""
    prio = {"music": 5, "bar": 4, "cultural": 4, "cinema": 4, "seasonal": 2, "civic": 1}
    return sorted(occasions, key=lambda o: (o.festive, prio.get(o.kind, 0)), reverse=True)


def template_concepts(dna: VenueDNA, occasions: list[Occasion], *, n: int = 5,
                      competitor_obs: list[dict] | None = None) -> list[EventConcept]:
    hint = ""
    if competitor_obs:
        names = [o.get("competitor") for o in competitor_obs if o.get("competitor")]
        if names:
            hint = (f"конкуренты ({', '.join(dict.fromkeys(names))}) активны — "
                    f"перехватите инфоповод собственным форматом")
    return [_template_concept(o, dna, hint) for o in _rank(occasions)[:n]]


# ── LLM-путь ──────────────────────────────────────────────────────────
def build_prompt(dna: VenueDNA, occasions: list[Occasion], *, n: int,
                 trends: list[str] | None = None,
                 competitor_obs: list[dict] | None = None) -> str:
    occ_lines = "\n".join(
        f"- {o.date} ({o.weekday}) {o.title} [{o.kind}] — {o.fit}" for o in occasions)
    trend_block = ""
    if trends:
        trend_block = "\nРастущие темы/тренды сейчас:\n" + "\n".join(f"- {t}" for t in trends)
    comp_block = ""
    if competitor_obs:
        names = dict.fromkeys(o.get("competitor", "") for o in competitor_obs if o.get("competitor"))
        if names:
            comp_block = ("\nКонкуренты активны: " + ", ".join(names) +
                          ". Предложи форматы, которых у них нет.")
    return (
        f"{dna.brief()}\n\n"
        f"Поводы ближайшего месяца:\n{occ_lines}{trend_block}{comp_block}\n\n"
        f"Придумай {n} конкретных концептов вечеров и коллабораций для этого заведения. "
        "Каждый — привязан к конкретной дате из списка поводов, в характере заведения, "
        "реалистичный для города. Верни СТРОГО JSON-массив объектов с полями: "
        "title, date (YYYY-MM-DD), occasion, kind (event|collab), pitch, "
        "mechanics (массив строк), collab (кто партнёр и зачем), differentiation "
        "(чего не делают конкуренты), kpi, risk, teaser (короткий анонс в голосе бренда), "
        "tags (массив). Только JSON, без пояснений."
    )


def _parse_json_array(text: str) -> list[dict]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("в ответе нет JSON-массива")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("ожидался массив")
    return data


def _concept_from_dict(d: dict) -> EventConcept:
    def s(key: str) -> str:
        v = d.get(key, "")
        return v.strip() if isinstance(v, str) else ""

    def lst(key: str) -> list[str]:
        v = d.get(key, [])
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return [str(v).strip()] if v else []

    return EventConcept(
        title=s("title") or "Вечер", date=s("date"), occasion=s("occasion"),
        kind=s("kind") or "event", pitch=s("pitch"), mechanics=lst("mechanics"),
        collab=s("collab"), differentiation=s("differentiation"), kpi=s("kpi"),
        risk=s("risk"), teaser=s("teaser"), tags=lst("tags"), source="llm",
    )


def llm_concepts(dna: VenueDNA, occasions: list[Occasion], *, n: int = 5,
                 trends: list[str] | None = None,
                 competitor_obs: list[dict] | None = None,
                 llm_key: str | None = None) -> list[EventConcept]:
    """Может бросить исключение — вызывающий откатывается на шаблон."""
    from agents.llm.service import chat, MAITRE_SYSTEM
    from agents.llm.base import ChatMessage
    prompt = build_prompt(dna, occasions, n=n, trends=trends, competitor_obs=competitor_obs)
    text = chat([ChatMessage("system", MAITRE_SYSTEM), ChatMessage("user", prompt)],
                key=llm_key, temperature=0.8, max_tokens=2000)
    data = _parse_json_array(text)
    concepts = [_concept_from_dict(d) for d in data if isinstance(d, dict)]
    # проставить день недели по дате, если LLM не дал
    from .calendar import WEEKDAYS_RU
    from datetime import date as _date
    for c in concepts:
        if c.date and not c.weekday:
            try:
                y, m, dd = (int(x) for x in c.date.split("-"))
                c.weekday = WEEKDAYS_RU[_date(y, m, dd).weekday()]
            except Exception:
                pass
    if not concepts:
        raise ValueError("LLM вернул пустой список")
    return concepts[:n]


def generate(dna: VenueDNA, occasions: list[Occasion], *, n: int = 5,
             trends: list[str] | None = None,
             competitor_obs: list[dict] | None = None,
             use_llm: bool = True, llm_key: str | None = None) -> tuple[list[EventConcept], str]:
    """Возвращает (концепты, режим). режим: 'llm' | 'template' | 'template (LLM недоступен)'."""
    if use_llm:
        try:
            return llm_concepts(dna, occasions, n=n, trends=trends,
                                competitor_obs=competitor_obs, llm_key=llm_key), "llm"
        except Exception as exc:
            log.info("LLM-движок недоступен, откат на шаблон: %s", exc)
            return template_concepts(dna, occasions, n=n, competitor_obs=competitor_obs), \
                "template (LLM недоступен)"
    return template_concepts(dna, occasions, n=n, competitor_obs=competitor_obs), "template"
