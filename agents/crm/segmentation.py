"""Сегментация гостей (rule-based)."""
from __future__ import annotations

from .models import Guest, VIP, REGULAR, CORPORATE, POTENTIAL, OCCASIONAL

# Пороги (премиальный сегмент)
PREMIUM_CHECK = 3000     # ₽ — «высокий чек»
FREQUENT_VISITS = 5      # визитов — «постоянный»
CORPORATE_MARKERS = ("корп", "компан", "банкет", "corporate", "b2b")


def classify(g: Guest) -> str:
    tags = (g.tags or "").lower()
    if any(m in tags for m in CORPORATE_MARKERS):
        return CORPORATE
    if g.avg_check >= PREMIUM_CHECK and g.visits >= FREQUENT_VISITS:
        return VIP
    if g.avg_check >= PREMIUM_CHECK and g.visits <= 2:
        return POTENTIAL
    if g.visits >= FREQUENT_VISITS:
        return REGULAR
    return OCCASIONAL


def apply_segments(guests: list[Guest]) -> list[Guest]:
    for g in guests:
        g.segment = classify(g)
    return guests
