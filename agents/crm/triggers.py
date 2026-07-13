"""Триггеры персональных касаний: день рождения и долгое отсутствие."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Guest

BIRTHDAY_LEAD_DAYS = 3   # напомнить за столько дней до ДР
ABSENCE_DAYS = 45        # «давно не было», если визитов не было столько дней

BIRTHDAY = "birthday"
ABSENCE = "absence"


@dataclass
class TriggerHit:
    guest_id: str
    name: str
    trigger: str        # birthday | absence
    detail: str

    def to_dict(self) -> dict:
        return {"guest_id": self.guest_id, "name": self.name,
                "trigger": self.trigger, "detail": self.detail}


def _days_until_birthday(birthday_mmdd: str, today: date) -> int | None:
    try:
        mo, d = (int(x) for x in birthday_mmdd.split("-"))
    except (ValueError, AttributeError):
        return None
    for year in (today.year, today.year + 1):
        try:
            bd = date(year, mo, d)
        except ValueError:
            return None  # напр. 29 февраля — пропускаем
        if bd >= today:
            return (bd - today).days
    return None


def find(guests: list[Guest], today: date) -> list[TriggerHit]:
    hits: list[TriggerHit] = []
    for g in guests:
        if g.birthday:
            days = _days_until_birthday(g.birthday, today)
            if days is not None and 0 <= days <= BIRTHDAY_LEAD_DAYS:
                when = "сегодня" if days == 0 else f"через {days} дн."
                hits.append(TriggerHit(g.id, g.name, BIRTHDAY, f"День рождения {when}"))
        if g.last_visit:
            try:
                lv = date.fromisoformat(g.last_visit)
            except ValueError:
                lv = None
            if lv:
                gone = (today - lv).days
                if gone > ABSENCE_DAYS:
                    hits.append(TriggerHit(g.id, g.name, ABSENCE, f"Не был(а) {gone} дн."))
    # Дни рождения — вперёд
    hits.sort(key=lambda h: 0 if h.trigger == BIRTHDAY else 1)
    return hits
