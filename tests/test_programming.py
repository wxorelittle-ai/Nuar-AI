"""Тесты идейного движка: календарь поводов, шаблонные и LLM-концепты."""
from __future__ import annotations

from agents.programming import calendar as cal
from agents.programming import engine
from agents.programming.models import VenueDNA, EventConcept


# ── Календарь ─────────────────────────────────────────────────────────
def test_occasions_halloween_in_october():
    occ = cal.occasions_for(2026, 10)
    titles = [o.title for o in occ]
    assert "Хэллоуин" in titles
    hw = next(o for o in occ if o.title == "Хэллоуин")
    assert hw.date == "2026-10-31" and hw.kind == "cultural"


def test_occasions_sorted_and_last_friday_present():
    occ = cal.occasions_for(2026, 11)
    dates = [o.date for o in occ]
    assert dates == sorted(dates)
    assert any("Afterwork" in o.title for o in occ)


def test_friday_13th_detected():
    # ноябрь 2026: 13-е — пятница
    occ = cal.occasions_for(2026, 11)
    assert any(o.title == "Пятница, 13-е" for o in occ)
    # февраль 2026: 13-е — пятница? проверим отсутствие ложных срабатываний в др. месяце
    occ_may = cal.occasions_for(2026, 5)
    f13 = [o for o in occ_may if o.title == "Пятница, 13-е"]
    for o in f13:
        y, m, d = (int(x) for x in o.date.split("-"))
        import datetime
        assert datetime.date(y, m, d).weekday() == 4


def test_every_month_has_enough_occasions():
    """В любом месяце должно набираться минимум 3 повода — иначе программа пустая."""
    for month in range(1, 13):
        occ = cal.occasions_for(2026, month)
        assert len(occ) >= 3, f"месяц {month}: поводов {len(occ)}"


def test_monthly_anchors_are_fridays():
    occ = cal.occasions_for(2026, 7)
    anchors = [o for o in occ if "первая пятница" in o.title or "последняя пятница" in o.title]
    assert len(anchors) == 2
    for a in anchors:
        assert a.weekday == "пт"


def test_world_gin_day_june_only():
    assert any(o.title == "World Gin Day" for o in cal.occasions_for(2026, 6))
    assert not any(o.title == "World Gin Day" for o in cal.occasions_for(2026, 7))


def test_nth_weekday_third_saturday():
    from datetime import date
    d = cal._nth_weekday(2026, 5, 5, 3)
    assert d.weekday() == 5 and 15 <= d.day <= 21


def test_may_has_victory_day_non_festive():
    occ = cal.occasions_for(2026, 5)
    vd = next(o for o in occ if o.title == "День Победы")
    assert vd.festive is False


def test_world_whisky_day_may_only():
    assert any(o.title == "World Whisky Day" for o in cal.occasions_for(2026, 5))
    assert not any(o.title == "World Whisky Day" for o in cal.occasions_for(2026, 6))


# ── ДНК ───────────────────────────────────────────────────────────────
def test_dna_from_dict_overrides_only_provided():
    dna = VenueDNA.from_dict({"name": "Noir Bar", "city": "Казань"})
    assert dna.name == "Noir Bar" and dna.city == "Казань"
    assert dna.concept  # дефолт остался
    assert "Noir Bar" in dna.brief()


# ── Шаблонный движок ──────────────────────────────────────────────────
def test_template_concepts_dated_and_ranked():
    dna = VenueDNA()
    occ = cal.occasions_for(2026, 10)
    concepts = engine.template_concepts(dna, occ, n=5)
    assert len(concepts) == min(5, len(occ))
    for c in concepts:
        assert isinstance(c, EventConcept)
        assert c.date and c.title and c.mechanics and c.kpi
        assert c.source == "template"


def test_template_partner_matches_music():
    dna = VenueDNA()
    music = cal.Occasion("Джаз", "2026-04-30", "music", "джем", "джаз-вечер")
    c = engine._template_concept(music, dna)
    assert "музык" in c.collab.lower()


def test_template_competitor_hint_used():
    dna = VenueDNA()
    occ = cal.occasions_for(2026, 10)
    concepts = engine.template_concepts(
        dna, occ, n=2, competitor_obs=[{"competitor": "Соседний бар"}])
    assert any("Соседний бар" in c.differentiation for c in concepts)


# ── Разбор JSON от LLM ────────────────────────────────────────────────
def test_parse_json_array_with_fence():
    text = "```json\n[{\"title\":\"X\"}]\n```"
    data = engine._parse_json_array(text)
    assert data == [{"title": "X"}]


def test_parse_json_array_with_prose_around():
    text = 'Вот идеи:\n[{"title":"Ночь джаза"}]\nГотово.'
    assert engine._parse_json_array(text)[0]["title"] == "Ночь джаза"


def test_llm_concepts_parses_and_fills_weekday(monkeypatch):
    payload = ('[{"title":"Нуар-детектив","date":"2026-10-31","kind":"event",'
               '"mechanics":["квиз","тёмные коктейли"],"collab":"книжный клуб",'
               '"teaser":"Скоро."}]')
    monkeypatch.setattr(engine, "chat", lambda *a, **k: payload, raising=False)
    import agents.llm.service as llm_service
    monkeypatch.setattr(llm_service, "chat", lambda *a, **k: payload)
    dna = VenueDNA()
    occ = cal.occasions_for(2026, 10)
    concepts = engine.llm_concepts(dna, occ, n=3)
    assert concepts[0].title == "Нуар-детектив"
    assert concepts[0].weekday == "сб"       # 2026-10-31 — суббота
    assert concepts[0].source == "llm"


def test_generate_falls_back_to_template_on_llm_error(monkeypatch):
    import agents.llm.service as llm_service
    def boom(*a, **k):
        raise RuntimeError("нет ключа")
    monkeypatch.setattr(llm_service, "chat", boom)
    dna = VenueDNA()
    occ = cal.occasions_for(2026, 10)
    concepts, mode = engine.generate(dna, occ, n=3, use_llm=True)
    assert len(concepts) == 3 and "template" in mode


def test_generate_template_only():
    dna = VenueDNA()
    occ = cal.occasions_for(2026, 2)   # февраль — насыщенный поводами месяц
    concepts, mode = engine.generate(dna, occ, n=4, use_llm=False)
    assert mode == "template" and len(concepts) == 4
