"""Тесты рекрутинг-агента (HH): парсинг и аналитика без сети."""
from __future__ import annotations

from agents.recruiting import hh
from agents.recruiting.models import Vacancy


# ── Сборка запроса ───────────────────────────────────────────────────
def test_build_vacancies_request():
    url, params = hh.build_vacancies_request("Официант", "95", per_page=100)
    assert url.endswith("/vacancies")
    assert params["text"] == "Официант"
    assert params["area"] == "95"
    assert params["per_page"] == 100


def test_build_caps_per_page():
    _, params = hh.build_vacancies_request("Повар", None, per_page=500)
    assert params["per_page"] == 100
    assert "area" not in params


# ── Парсинг ответа ───────────────────────────────────────────────────
SAMPLE = {
    "found": 137,
    "items": [
        {"name": "Официант", "employer": {"name": "Арбат"},
         "salary": {"from": 50000, "to": 70000, "currency": "RUR", "gross": False},
         "area": {"name": "Тюмень"}, "alternate_url": "u1", "published_at": "2026-07-10"},
        {"name": "Официант", "employer": {"name": "Сыроварня"},
         "salary": {"from": 60000, "to": None, "currency": "RUR", "gross": True},
         "area": {"name": "Тюмень"}, "alternate_url": "u2"},
        {"name": "Официант", "employer": {"name": "Арбат"},
         "salary": None, "area": {"name": "Тюмень"}, "alternate_url": "u3"},
        {"name": "Официант", "employer": {"name": "Bar USD"},
         "salary": {"from": 1000, "to": 2000, "currency": "USD", "gross": False}},
    ],
}


def test_parse_vacancies():
    found, vacs = hh.parse_vacancies(SAMPLE)
    assert found == 137
    assert len(vacs) == 4
    assert vacs[0].employer == "Арбат"
    assert vacs[0].salary_from == 50000 and vacs[0].gross is False


def test_salary_points_filters_currency_and_applies_gross():
    _, vacs = hh.parse_vacancies(SAMPLE)
    pts = hh.salary_points(vacs)
    # USD и вакансия без зарплаты исключены → остаётся 2 точки
    assert len(pts) == 2
    assert 59000 <= pts[0] <= 61000            # (50000+70000)/2 = 60000, net
    assert abs(pts[1] - 60000 * 0.87) < 1      # gross 60000 → net ≈ 52200


def test_top_employers_counts():
    _, vacs = hh.parse_vacancies(SAMPLE)
    tops = hh.top_employers(vacs)
    assert tops[0] == {"name": "Арбат", "count": 2}
    names = {t["name"] for t in tops}
    assert "Сыроварня" in names


def test_role_market_aggregate():
    _, vacs = hh.parse_vacancies(SAMPLE)
    rm = hh.role_market("Официант", vacs, 137)
    assert rm.found == 137
    assert rm.with_salary == 2
    assert rm.salary_median is not None
    assert rm.salary_median % 100 == 0          # округление до сотен
    assert rm.top_employers[0]["name"] == "Арбат"


def test_role_market_no_salary():
    vacs = [Vacancy(name="Повар", employer="X", salary_from=None, salary_to=None)]
    rm = hh.role_market("Повар", vacs, 5)
    assert rm.with_salary == 0
    assert rm.salary_median is None


def test_area_fallback():
    # оффлайн: suggest_area падает на сети → берётся запасной id
    import agents.recruiting.hh as hhmod
    assert hhmod.AREA_FALLBACK["тюмень"] == "95"


# ── Токен приложения HH (обход 403) ──────────────────────────────────
def test_headers_include_bearer_when_token(monkeypatch):
    monkeypatch.setattr(hh, "_app_token", lambda: "TOK123")
    h = hh._headers()
    assert h["Authorization"] == "Bearer TOK123"
    assert h["User-Agent"]


def test_headers_no_auth_without_token(monkeypatch):
    monkeypatch.setattr(hh, "_app_token", lambda: None)
    assert "Authorization" not in hh._headers()
