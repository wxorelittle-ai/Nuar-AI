"""Сервис VIP CRM: импорт, сегменты, триггеры, персональные сообщения."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone, date

from .models import Guest, SEGMENTS
from . import csv_import, segmentation, triggers
from .store import store

log = logging.getLogger("restopulse.crm")

# Голос метрдотеля для персональных сообщений (бренд: без скидок, без эмодзи)
MAITRE_CRM = (
    "Ты — метрдотель премиального ресторана. Пишешь личное сообщение конкретному "
    "гостю по имени: тепло, уважительно, сдержанно, от первого лица. НИКАКИХ скидок "
    "и акций, без эмодзи и восклицаний, без канцелярита. 2–3 предложения."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Импорт ────────────────────────────────────────────────────────────
def import_csv(text: str) -> dict:
    guests = csv_import.parse_csv(text, now_iso=_now_iso())
    if not guests:
        return {"imported": 0, "error": "Не удалось распознать гостей. Проверьте заголовки и формат CSV."}
    segmentation.apply_segments(guests)
    store.replace_all(guests)
    return {"imported": len(guests), "summary": summary(guests)}


def summary(guests: list[Guest] | None = None) -> dict:
    guests = guests if guests is not None else store.list()
    counts = Counter(g.segment for g in guests)
    return {
        "total": len(guests),
        "segments": [{"key": k, "label": v, "count": counts.get(k, 0)} for k, v in SEGMENTS.items()],
    }


def list_guests() -> list[dict]:
    return [g.to_dict() for g in store.list()]


# ── Триггеры ──────────────────────────────────────────────────────────
def due_touches(today: date | None = None) -> list[dict]:
    today = today or datetime.now(timezone.utc).date()
    return [h.to_dict() for h in triggers.find(store.list(), today)]


# ── Персональное сообщение (черновик) ─────────────────────────────────
def _template(name: str, trigger: str) -> str:
    first = (name or "гость").split()[0]
    if trigger == triggers.BIRTHDAY:
        return (f"{first}, добрый день. Поздравляю вас с наступающим днём рождения. "
                "Будем рады видеть вас у нас — подготовлю столик и особенный вечер. "
                "С уважением, метрдотель.")
    return (f"{first}, добрый день. Давно не видели вас в нашем зале. "
            "В ближайшую пятницу — вечер живой музыки; с удовольствием оставлю для вас столик. "
            "С уважением, метрдотель.")


def generate_message(guest_id: str, trigger: str) -> dict:
    g = store.get(guest_id)
    if g is None:
        return {"error": "Гость не найден"}
    template = _template(g.name, trigger)

    # Пытаемся улучшить активной моделью; при отсутствии — шаблон.
    try:
        from agents.llm import service as llm
        from agents.llm.base import ChatMessage
        occasion = ("день рождения гостя (за несколько дней до даты)"
                    if trigger == triggers.BIRTHDAY else
                    "гость давно не приходил — пригласить на вечер с живой музыкой")
        prompt = (f"Имя гостя: {g.name}. Повод: {occasion}. "
                  f"Сегмент: {SEGMENTS.get(g.segment, g.segment)}. "
                  "Напиши личное сообщение от метрдотеля. Только текст сообщения.")
        text = llm.chat([ChatMessage("system", MAITRE_CRM), ChatMessage("user", prompt)],
                        temperature=0.7, max_tokens=300).strip()
        return {"draft": text, "source": "ai"}
    except Exception as exc:  # нет активного ассистента / сеть — отдаём шаблон
        log.debug("CRM: AI недоступен, шаблон. %s", exc)
        return {"draft": template, "source": "template"}
