"""Тесты VIP CRM: импорт CSV, сегментация, триггеры (без сети)."""
from __future__ import annotations

from datetime import date

from agents.crm import csv_import, segmentation, triggers
from agents.crm.models import Guest, VIP, CORPORATE, POTENTIAL, REGULAR, OCCASIONAL


# ── Парсинг CSV ──────────────────────────────────────────────────────
CSV_COMMA = """Имя,Телефон,День рождения,Последний визит,Визитов,Средний чек,Теги
Соколов Иван,+79001234567,16.07.1980,2026-07-01,12,5 200,
Петрова Анна,,20.11.1990,01.05.2026,2,4800,vip-потенциал
"""

CSV_SEMI = "name;visits;avg_check\nИванов;7;2200\n"


def test_parse_csv_comma_and_headers():
    guests = csv_import.parse_csv(CSV_COMMA)
    assert len(guests) == 2
    g = guests[0]
    assert g.name == "Соколов Иван"
    assert g.phone == "+79001234567"
    assert g.birthday == "07-16"          # MM-DD
    assert g.last_visit == "2026-07-01"
    assert g.visits == 12
    assert g.avg_check == 5200             # «5 200» → 5200


def test_parse_csv_semicolon_delimiter():
    guests = csv_import.parse_csv(CSV_SEMI)
    assert len(guests) == 1
    assert guests[0].name == "Иванов" and guests[0].visits == 7


def test_parse_dates_formats():
    assert csv_import.parse_date("2026-07-13") == "2026-07-13"
    assert csv_import.parse_date("13.07.2026") == "2026-07-13"
    assert csv_import.parse_date("13/07/26") == "2026-07-13"
    assert csv_import.parse_date("ерунда") == ""
    assert csv_import.parse_birthday("05.02.1988") == "02-05"
    assert csv_import.parse_birthday("16.07") == "07-16"


def test_skip_rows_without_name():
    guests = csv_import.parse_csv("Имя,Визитов\n,5\nПётр,3\n")
    assert [g.name for g in guests] == ["Пётр"]


# ── Сегментация ──────────────────────────────────────────────────────
def test_segments():
    assert segmentation.classify(Guest(id="1", avg_check=5200, visits=12)) == VIP
    assert segmentation.classify(Guest(id="2", avg_check=4800, visits=2)) == POTENTIAL
    assert segmentation.classify(Guest(id="3", avg_check=2200, visits=7)) == REGULAR
    assert segmentation.classify(Guest(id="4", avg_check=1500, visits=1)) == OCCASIONAL
    assert segmentation.classify(Guest(id="5", avg_check=15000, visits=3, tags="корпоратив")) == CORPORATE


# ── Триггеры ─────────────────────────────────────────────────────────
def test_birthday_trigger_within_lead():
    today = date(2026, 7, 13)
    g = Guest(id="1", name="Соколов Иван", birthday="07-16")   # через 3 дня
    hits = triggers.find([g], today)
    assert any(h.trigger == triggers.BIRTHDAY for h in hits)


def test_birthday_not_triggered_far():
    today = date(2026, 7, 13)
    g = Guest(id="1", name="X", birthday="11-20")
    assert not [h for h in triggers.find([g], today) if h.trigger == triggers.BIRTHDAY]


def test_absence_trigger():
    today = date(2026, 7, 13)
    g = Guest(id="1", name="Анна", last_visit="2026-05-01")    # >45 дней
    hits = triggers.find([g], today)
    ab = [h for h in hits if h.trigger == triggers.ABSENCE]
    assert ab and "дн." in ab[0].detail


def test_recent_visit_no_absence():
    today = date(2026, 7, 13)
    g = Guest(id="1", name="Дмитрий", last_visit="2026-07-05")
    assert not [h for h in triggers.find([g], today) if h.trigger == triggers.ABSENCE]


def test_triggers_birthday_sorted_first():
    today = date(2026, 7, 13)
    guests = [Guest(id="a", name="Absent", last_visit="2026-01-01"),
              Guest(id="b", name="Bday", birthday="07-14")]
    hits = triggers.find(guests, today)
    assert hits[0].trigger == triggers.BIRTHDAY
