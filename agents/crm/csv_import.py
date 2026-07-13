"""Импорт гостевой базы из CSV с гибким сопоставлением колонок.

Понимает русские и английские заголовки, разделители «,» и «;», основные
форматы дат. Пустые/битые значения не роняют импорт.
"""
from __future__ import annotations

import csv
import io
import re
import uuid

from .models import Guest

# Сопоставление: поле → возможные заголовки (в нижнем регистре, без пробелов по краям)
HEADER_MAP = {
    "name": {"имя", "name", "гость", "фио", "имя гостя"},
    "phone": {"телефон", "phone", "тел", "контакт", "contact", "номер"},
    "email": {"email", "e-mail", "почта", "мейл"},
    "birthday": {"др", "день рождения", "дата рождения", "birthday", "birth", "др гостя"},
    "last_visit": {"последний визит", "последнее посещение", "last_visit", "был", "последний раз", "дата визита"},
    "visits": {"визитов", "визиты", "посещений", "visits", "кол-во визитов", "количество визитов"},
    "avg_check": {"средний чек", "avg_check", "чек", "средний_чек", "average check"},
    "tags": {"теги", "tags", "метки", "заметка", "note", "комментарий", "сегмент"},
}


def _norm(h: str) -> str:
    return (h or "").strip().lower().replace("ё", "е")


def _resolve_headers(fieldnames: list[str]) -> dict:
    """Возвращает {field: имя_колонки_в_файле}."""
    resolved = {}
    for raw in fieldnames or []:
        n = _norm(raw)
        for field, variants in HEADER_MAP.items():
            if field in resolved:
                continue
            if n in variants:
                resolved[field] = raw
                break
    return resolved


def _to_int(v: str) -> int:
    digits = re.sub(r"[^\d]", "", str(v or ""))
    return int(digits) if digits else 0


def parse_date(v: str) -> str:
    """Возвращает ISO-дату 'YYYY-MM-DD' или ''. Принимает 2026-07-13, 13.07.2026, 13/07/2026."""
    v = (v or "").strip()
    if not v:
        return ""
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", v)
    if m:
        y, mo, d = m.groups()
    else:
        m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})$", v)
        if not m:
            return ""
        d, mo, y = m.groups()
        if len(y) == 2:
            y = "20" + y
    try:
        mo_i, d_i = int(mo), int(d)
        if not (1 <= mo_i <= 12 and 1 <= d_i <= 31):
            return ""
        return f"{int(y):04d}-{mo_i:02d}-{d_i:02d}"
    except ValueError:
        return ""


def parse_birthday(v: str) -> str:
    """Возвращает 'MM-DD' из даты рождения (год не важен). Принимает и 'DD.MM'."""
    iso = parse_date(v)
    if iso:
        return iso[5:]
    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})$", (v or "").strip())
    if m:
        d, mo = m.groups()
        try:
            if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
                return f"{int(mo):02d}-{int(d):02d}"
        except ValueError:
            pass
    return ""


def parse_csv(text: str, now_iso: str = "") -> list[Guest]:
    """Разбирает CSV-текст в список гостей."""
    if not text or not text.strip():
        return []
    # Определяем разделитель (Excel в РФ часто пишет ;)
    sample = text[:2000]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    cols = _resolve_headers(reader.fieldnames or [])

    guests: list[Guest] = []
    for row in reader:
        def val(field):
            col = cols.get(field)
            return (row.get(col) or "").strip() if col else ""

        name = val("name")
        if not name:
            continue  # без имени запись бессмысленна
        guests.append(Guest(
            id=uuid.uuid4().hex[:12],
            name=name,
            phone=val("phone"),
            email=val("email"),
            birthday=parse_birthday(val("birthday")),
            last_visit=parse_date(val("last_visit")),
            visits=_to_int(val("visits")),
            avg_check=_to_int(val("avg_check")),
            tags=val("tags"),
            created_at=now_iso,
        ))
    return guests
