"""Контент-кампания из концепта вечера.

Замыкает петлю «идея → контент»: концепт превращается в серию постов с датами
(тизер → анонс → напоминание → день события → репортаж), которые падают
черновиками в обычную очередь контента и дальше идут через модерацию и
публикацию.

Биты, у которых расчётная дата уже прошла, пропускаются — если до события 3 дня,
тизер за 10 дней не нужен.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone

from .models import VenueDNA, EventConcept

log = logging.getLogger("restopulse.programming.campaign")

# Биты кампании: ключ, сдвиг в днях от даты события, заголовок, контент-линия, час публикации
STAGES = [
    ("teaser",   -10, "Тизер",            "Событийность", 19),
    ("announce",  -7, "Анонс",            "Событийность", 19),
    ("reminder",  -1, "Напоминание",      "Событийность", 18),
    ("dayof",      0, "В день события",   "Атмосфера",    16),
    ("recap",      1, "Пост-репортаж",    "Гость",        14),
]


@dataclass
class Beat:
    """Один пост кампании."""

    stage: str
    label: str
    network: str
    content_line: str
    topic: str
    text: str
    scheduled_at: str        # ISO datetime

    def to_dict(self) -> dict:
        return asdict(self)


def _event_date(concept: EventConcept) -> date | None:
    try:
        y, m, d = (int(x) for x in concept.date.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def _beat_text(stage: str, concept: EventConcept, dna: VenueDNA) -> str:
    """Детерминированный текст бита в голосе бренда (без LLM)."""
    when = concept.date
    mech = "; ".join(concept.mechanics[:2]) if concept.mechanics else ""
    if stage == "teaser":
        return (f"{when} в «{dna.name}» — вечер, о котором пока умолчим. "
                f"Скажем лишь: {concept.occasion or concept.title}. Подробности вскоре.")
    if stage == "announce":
        base = concept.teaser or f"{when} — «{concept.title}» в «{dna.name}»."
        detail = f" В программе: {mech}." if mech else ""
        return f"{base}{detail} Бронь столика — заранее."
    if stage == "reminder":
        return (f"Завтра в «{dna.name}» — «{concept.title}». "
                f"Свободные столы ещё есть, но их немного.")
    if stage == "dayof":
        return (f"Сегодня. «{concept.title}» в «{dna.name}». "
                f"Двери открыты, свет приглушён — ждём вас вечером.")
    if stage == "recap":
        return (f"«{concept.title}» состоялся. Благодарим всех, кто был с нами вечером в «{dna.name}». "
                f"Фотографии — в альбоме, а мы уже готовим следующий вечер.")
    return concept.teaser or concept.title


def plan_campaign(concept: EventConcept, dna: VenueDNA, *, networks: list[str] | None = None,
                  today: date | None = None, texts: dict[str, str] | None = None) -> list[Beat]:
    """Чистая сборка плана (тестируется без сети).

    texts — необязательные тексты от LLM по ключу бита; чего нет, берётся из шаблона.
    """
    networks = networks or ["vk"]
    today = today or datetime.now(timezone.utc).date()
    ev = _event_date(concept)
    if ev is None:
        return []
    texts = texts or {}
    beats: list[Beat] = []
    for stage, shift, label, line, hour in STAGES:
        when = ev + timedelta(days=shift)
        if when < today:
            continue                                  # бит уже в прошлом — пропускаем
        text = texts.get(stage) or _beat_text(stage, concept, dna)
        sched = datetime(when.year, when.month, when.day, hour, 0,
                         tzinfo=timezone.utc).isoformat()
        for net in networks:
            beats.append(Beat(stage=stage, label=label, network=net, content_line=line,
                              topic=f"{concept.title} — {label.lower()}",
                              text=text, scheduled_at=sched))
    return beats


# ── LLM-путь ──────────────────────────────────────────────────────────
def build_prompt(concept: EventConcept, dna: VenueDNA, stages: list[str]) -> str:
    mech = "; ".join(concept.mechanics) if concept.mechanics else "—"
    names = {"teaser": "тизер за 10 дней (интрига, без полного раскрытия)",
             "announce": "анонс за неделю (полные детали, призыв забронировать)",
             "reminder": "напоминание за день (последний шанс)",
             "dayof": "пост в день события (сегодня, двери открыты)",
             "recap": "пост-репортаж на следующий день (благодарность, итог)"}
    asked = "\n".join(f"- {s}: {names.get(s, s)}" for s in stages)
    return (
        f"{dna.brief()}\n\n"
        f"Событие: «{concept.title}», дата {concept.date}. Суть: {concept.pitch}. "
        f"Механика: {mech}. Повод: {concept.occasion}.\n\n"
        f"Напиши тексты постов для соцсетей по этим этапам:\n{asked}\n\n"
        "Каждый — 2–4 предложения, в голосе бренда, без эмодзи и восклицательных знаков. "
        "Верни СТРОГО JSON-объект вида {\"ключ_этапа\": \"текст\"}. Только JSON."
    )


def _parse_json_object(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("в ответе нет JSON-объекта")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("ожидался объект")
    return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}


def llm_texts(concept: EventConcept, dna: VenueDNA, stages: list[str],
              *, llm_key: str | None = None) -> dict[str, str]:
    """Может бросить исключение — вызывающий откатится на шаблон."""
    from agents.llm.service import chat, MAITRE_SYSTEM
    from agents.llm.base import ChatMessage
    text = chat([ChatMessage("system", MAITRE_SYSTEM),
                 ChatMessage("user", build_prompt(concept, dna, stages))],
                key=llm_key, temperature=0.75, max_tokens=1200)
    return _parse_json_object(text)


def build(concept: EventConcept, dna: VenueDNA, *, networks: list[str] | None = None,
          use_llm: bool = True, today: date | None = None,
          llm_key: str | None = None) -> tuple[list[Beat], str]:
    """Возвращает (биты, режим). режим: 'llm' | 'template' | 'template (LLM недоступен)'."""
    today = today or datetime.now(timezone.utc).date()
    ev = _event_date(concept)
    if ev is None:
        return [], "template"
    stages = [s for s, shift, *_ in STAGES if ev + timedelta(days=shift) >= today]
    if use_llm and stages:
        try:
            texts = llm_texts(concept, dna, stages, llm_key=llm_key)
            return plan_campaign(concept, dna, networks=networks, today=today, texts=texts), "llm"
        except Exception as exc:
            log.info("LLM-кампания недоступна, откат на шаблон: %s", exc)
            return (plan_campaign(concept, dna, networks=networks, today=today),
                    "template (LLM недоступен)")
    return plan_campaign(concept, dna, networks=networks, today=today), "template"


def save_as_drafts(beats: list[Beat]) -> list[dict]:
    """Кладёт биты черновиками в обычную очередь контента."""
    from agents.content import service as content
    saved = []
    for b in beats:
        post = content.save_post({
            "network": b.network, "content_line": b.content_line,
            "topic": b.topic, "text": b.text, "scheduled_at": b.scheduled_at,
            "status": "draft",
        })
        saved.append(post.to_dict())
    return saved
