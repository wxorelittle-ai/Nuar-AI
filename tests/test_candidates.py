"""Тесты витрины вакансий и кандидатов: хранение, оценка, рейтинг."""
from __future__ import annotations

import pytest

from agents.recruiting import candidates as cand


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Отдельное JSON-хранилище на каждый тест, без БД и без реальных данных."""
    monkeypatch.setattr("db.database.db_enabled", lambda: False)
    s = cand.ScreeningStore(path=tmp_path / "recruiting.json")
    monkeypatch.setattr(cand, "store", s)
    return s


def _vacancy():
    return cand.create_vacancy({
        "title": "Бармен", "must_have": ["бармен", "коктейл"],
        "nice_to_have": ["кофе"], "min_experience": 2, "city": "Тюмень"})


def test_create_and_list_vacancy():
    v = _vacancy()
    assert v.id and v.title == "Бармен"
    assert v.must_have == ["бармен", "коктейл"]
    assert [x.id for x in cand.store.list_vacancies()] == [v.id]


def test_vacancy_accepts_comma_string_for_skills():
    v = cand.create_vacancy({"title": "Повар", "must_have": "жарка, гриль ,   соусы"})
    assert v.must_have == ["жарка", "гриль", "соусы"]


def test_add_candidate_evaluates_fit_and_ai():
    v = _vacancy()
    c = cand.add_candidate(v.id, name="Иван",
                           text="Бармен, опыт 4 года, готовлю коктейли, знаю кофе.")
    assert c.fit["score"] == 100
    assert c.fit["matched_must"] == ["бармен", "коктейл"]
    assert "level" in c.ai


def test_add_candidate_requires_vacancy_and_text():
    with pytest.raises(ValueError):
        cand.add_candidate("нет-такой", name="X", text="текст")
    v = _vacancy()
    with pytest.raises(ValueError):
        cand.add_candidate(v.id, name="X", text="   ")


def test_ranking_orders_by_fit_and_flags_duplicates():
    v = _vacancy()
    strong = "Бармен, опыт 5 лет, готовлю коктейли, разбираюсь в кофе."
    cand.add_candidate(v.id, name="Сильный", text=strong)
    cand.add_candidate(v.id, name="Списал", text=strong + " Также люблю чай.")  # копия
    cand.add_candidate(v.id, name="Слабый", text="Ищу подработку, опыта нет.")

    r = cand.ranking(v.id)
    assert r["count"] == 3
    names = [c["name"] for c in r["candidates"]]
    assert names[-1] == "Слабый"                       # слабый — в хвосте
    assert r["candidates"][0]["rank"] == 1
    # дубликат между «Сильный» и «Списал» найден
    assert r["duplicates_found"] >= 1
    dup_names = {c["name"] for c in r["candidates"] if c["duplicate"]}
    assert {"Сильный", "Списал"} <= dup_names


def test_reevaluate_after_requirement_change():
    v = _vacancy()
    c = cand.add_candidate(v.id, name="Кофеман", text="Бариста, кофе, латте-арт, опыт 3 года")
    assert c.fit["score"] < 100                          # нет обязательных «бармен/коктейл»
    # смягчаем требования
    v2 = cand.create_vacancy({"id": v.id, "title": "Бариста",
                              "must_have": ["кофе"], "min_experience": 2})
    n = cand.reevaluate_vacancy(v2.id)
    assert n == 1
    updated = cand.store.candidates_for(v.id)[0]
    assert updated.fit["score"] == 100                   # теперь полностью подходит


def test_delete_vacancy_cascades_candidates():
    v = _vacancy()
    cand.add_candidate(v.id, name="Иван", text="бармен коктейли опыт 3 года")
    assert cand.store.candidates_for(v.id)
    assert cand.store.delete_vacancy(v.id) is True
    assert cand.store.candidates_for(v.id) == []
    assert cand.store.get_vacancy(v.id) is None


def test_persistence_across_store_instances(tmp_path, monkeypatch):
    monkeypatch.setattr("db.database.db_enabled", lambda: False)
    s1 = cand.ScreeningStore(path=tmp_path / "r.json")
    monkeypatch.setattr(cand, "store", s1)
    v = _vacancy()
    cand.add_candidate(v.id, name="Иван", text="бармен коктейли опыт 3 года")
    # новый инстанс на том же файле видит данные
    s2 = cand.ScreeningStore(path=tmp_path / "r.json")
    assert [x.id for x in s2.list_vacancies()] == [v.id]
    assert len(s2.candidates_for(v.id)) == 1
