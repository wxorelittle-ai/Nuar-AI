"""Тесты конвейера оценки кандидатов: соответствие, ИИ-сигналы, дубликаты."""
from __future__ import annotations

from agents.recruiting import screening as sc


# ── Соответствие вакансии ─────────────────────────────────────────────
def test_experience_years_extracts_max():
    assert sc.experience_years("Опыт работы 3 года, до этого стаж 5 лет") == 5.0
    assert sc.experience_years("без опыта") is None
    assert sc.experience_years("работал 2 года барменом") == 2.0


def test_fit_full_match():
    resume = "Бармен, опыт 4 года. Готовлю классические коктейли, знаю кофе."
    r = sc.score_fit(resume, must_have=["бармен", "коктейл"],
                     nice_to_have=["кофе"], min_experience=2)
    assert r.matched_must == ["бармен", "коктейл"]
    assert r.missing_must == []
    assert r.matched_nice == ["кофе"]
    assert r.experience_ok is True
    assert r.score == 100


def test_fit_missing_must_have_dominates():
    resume = "Отличный кофе и латте-арт, опыт 5 лет."
    r = sc.score_fit(resume, must_have=["сомелье", "вино"], nice_to_have=["кофе"])
    assert r.matched_must == []
    assert set(r.missing_must) == {"сомелье", "вино"}
    # без обязательных навыков балл низкий несмотря на желательные
    assert r.score <= 40


def test_fit_experience_below_minimum():
    r = sc.score_fit("бармен, опыт 1 год", must_have=["бармен"], min_experience=3)
    assert r.experience_ok is False
    assert r.score < 100


def test_fit_no_requirements_is_neutral_high():
    r = sc.score_fit("любой текст")
    assert r.score == 100    # нет требований — некого отсекать


# ── Признаки ИИ-текста ────────────────────────────────────────────────
def test_ai_signals_flags_buzzword_soup():
    text = ("Я коммуникабельный, стрессоустойчивый и ответственный командный игрок, "
            "нацелен на результат, быстро обучаем и клиентоориентирован.")
    r = sc.ai_signals(text)
    assert r.score >= 30
    assert r.level in ("средняя", "высокая")
    assert any("клише" in f for f in r.flags)


def test_ai_signals_specific_resume_scores_low():
    text = ("Работал барменом в баре Nuar 3 года. За смену готовил до 120 коктейлей, "
            "поднял средний чек на 15%. Прошёл курс по миксологии в 2024 году в Тюмени.")
    r = sc.ai_signals(text)
    assert r.level == "низкая"


def test_ai_signals_has_disclaimer():
    r = sc.ai_signals("любой текст")
    assert "не приговор" in r.disclaimer


def test_ai_signals_no_numbers_flag():
    text = ("Ответственный сотрудник с большим опытом работы в сфере обслуживания гостей. "
            "Всегда нахожу подход к посетителям и решаю любые задачи качественно и вовремя, "
            "постоянно развиваюсь и стремлюсь к лучшему результату в своей профессиональной "
            "области. Умею работать в команде и самостоятельно, легко осваиваю новое, "
            "внимателен к деталям и ценю честность, порядок и уважение к каждому человеку.")
    r = sc.ai_signals(text)
    assert any("цифр" in f for f in r.flags)


# ── Дубликаты (списывание) ────────────────────────────────────────────
def test_similarity_identical_is_one():
    t = "опыт работы барменом три года готовлю коктейли"
    assert sc.similarity(t, t) == 1.0


def test_similarity_different_is_low():
    a = "опыт работы барменом три года готовлю коктейли"
    b = "повар горячего цеха стаж пять лет банкеты"
    assert sc.similarity(a, b) < 0.2


def test_find_duplicates_flags_copies():
    base = "опыт работы барменом три года готовлю классические коктейли знаю кофе"
    items = [
        {"id": "1", "name": "Иван", "text": base},
        {"id": "2", "name": "Пётр", "text": base + " и чай"},   # почти копия
        {"id": "3", "name": "Анна", "text": "шеф-повар банкеты авторское меню десять лет"},
    ]
    dups = sc.find_duplicates(items)
    assert "1" in dups and "2" in dups          # Иван и Пётр — совпадение
    assert dups["1"].other_id == "2"
    assert "3" not in dups                       # Анна уникальна


def test_find_duplicates_empty_and_single():
    assert sc.find_duplicates([]) == {}
    assert sc.find_duplicates([{"id": "1", "name": "A", "text": "текст один два три"}]) == {}
