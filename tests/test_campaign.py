"""Тесты контент-кампании из концепта вечера."""
from __future__ import annotations

from datetime import date

from agents.programming import campaign as camp
from agents.programming.models import VenueDNA, EventConcept


def _concept(**kw) -> EventConcept:
    base = dict(title="Нуар-детектив", date="2026-10-31", occasion="Хэллоуин",
                pitch="Вечер-расследование", mechanics=["квиз по уликам", "тёмные коктейли"],
                teaser="31 октября — вечер-расследование в «Nuar».")
    base.update(kw)
    return EventConcept(**base)


def test_full_campaign_has_all_stages_when_early():
    beats = camp.plan_campaign(_concept(), VenueDNA(), today=date(2026, 10, 1))
    assert [b.stage for b in beats] == ["teaser", "announce", "reminder", "dayof", "recap"]


def test_past_beats_are_skipped():
    """До события 3 дня — тизер (−10) и анонс (−7) уже в прошлом."""
    beats = camp.plan_campaign(_concept(), VenueDNA(), today=date(2026, 10, 28))
    assert [b.stage for b in beats] == ["reminder", "dayof", "recap"]


def test_no_beats_after_event_recap_window():
    beats = camp.plan_campaign(_concept(), VenueDNA(), today=date(2026, 11, 5))
    assert beats == []


def test_multiple_networks_multiply_beats():
    beats = camp.plan_campaign(_concept(), VenueDNA(), networks=["vk", "telegram"],
                               today=date(2026, 10, 1))
    assert len(beats) == 10
    assert {b.network for b in beats} == {"vk", "telegram"}


def test_scheduled_at_is_iso_and_ordered():
    beats = camp.plan_campaign(_concept(), VenueDNA(), today=date(2026, 10, 1))
    times = [b.scheduled_at for b in beats]
    assert times == sorted(times)
    assert times[0].startswith("2026-10-21")     # 31 октября минус 10 дней
    assert times[-1].startswith("2026-11-01")    # репортаж на следующий день


def test_no_date_gives_no_campaign():
    assert camp.plan_campaign(_concept(date=""), VenueDNA(), today=date(2026, 10, 1)) == []


def test_template_texts_mention_venue_and_event():
    beats = camp.plan_campaign(_concept(), VenueDNA(name="Nuar"), today=date(2026, 10, 1))
    joined = " ".join(b.text for b in beats)
    assert "Nuar" in joined and "Нуар-детектив" in joined


def test_llm_texts_used_when_provided():
    beats = camp.plan_campaign(_concept(), VenueDNA(), today=date(2026, 10, 1),
                               texts={"teaser": "ТЕКСТ ОТ AI"})
    teaser = next(b for b in beats if b.stage == "teaser")
    assert teaser.text == "ТЕКСТ ОТ AI"
    # остальные — из шаблона
    assert next(b for b in beats if b.stage == "recap").text != "ТЕКСТ ОТ AI"


def test_parse_json_object_with_fence():
    assert camp._parse_json_object('```json\n{"teaser":"x"}\n```') == {"teaser": "x"}


def test_parse_json_object_drops_non_strings():
    assert camp._parse_json_object('{"a":"ok","b":5,"c":""}') == {"a": "ok"}


def test_build_falls_back_to_template_on_llm_error(monkeypatch):
    import agents.llm.service as llm_service
    monkeypatch.setattr(llm_service, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("нет ключа")))
    beats, mode = camp.build(_concept(), VenueDNA(), use_llm=True, today=date(2026, 10, 1))
    assert "template" in mode and len(beats) == 5


def test_build_llm_mode(monkeypatch):
    import agents.llm.service as llm_service
    payload = '{"teaser":"T","announce":"A","reminder":"R","dayof":"D","recap":"C"}'
    monkeypatch.setattr(llm_service, "chat", lambda *a, **k: payload)
    beats, mode = camp.build(_concept(), VenueDNA(), use_llm=True, today=date(2026, 10, 1))
    assert mode == "llm"
    assert [b.text for b in beats] == ["T", "A", "R", "D", "C"]


def test_build_prompt_only_asks_remaining_stages():
    p = camp.build_prompt(_concept(), VenueDNA(), ["reminder", "dayof"])
    assert "reminder" in p and "dayof" in p and "teaser" not in p
