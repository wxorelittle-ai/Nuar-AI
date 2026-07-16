"""Тесты погодного сигнала (Open-Meteo)."""
from __future__ import annotations

import pytest

from agents.weather import service as w


@pytest.fixture(autouse=True)
def _clear_cache():
    w._geo_cache.clear()
    w._forecast_cache.clear()
    yield
    w._geo_cache.clear()
    w._forecast_cache.clear()


# ── Советы по формату ─────────────────────────────────────────────────
def test_storm_kills_outdoor():
    adv, outdoor = w.advice_for(95, 22.0, 18.0, 10.0)
    assert outdoor is False and "открытая площадка отпадает" in adv


def test_heavy_precip_kills_outdoor_even_without_storm_code():
    adv, outdoor = w.advice_for(63, 20.0, 12.0, 5.0)
    assert outdoor is False and "открытая площадка отпадает" in adv


def test_rain_suggests_indoor():
    adv, outdoor = w.advice_for(61, 18.0, 2.0, 5.0)
    assert outdoor is False and "камерный зал" in adv


def test_warm_and_dry_enables_terrace():
    adv, outdoor = w.advice_for(0, 24.0, 0.0, 8.0)
    assert outdoor is True and "веранда" in adv


def test_heat_advice():
    adv, outdoor = w.advice_for(0, 32.0, 0.0, 5.0)
    assert "жара" in adv and outdoor is True


def test_cold_advice():
    adv, outdoor = w.advice_for(3, 2.0, 0.0, 5.0)
    assert "холодно" in adv and outdoor is False


def test_strong_wind_blocks_outdoor():
    adv, outdoor = w.advice_for(1, 18.0, 0.0, 35.0)
    assert outdoor is False and "ветер" in adv


# ── Разбор прогноза ───────────────────────────────────────────────────
def _payload():
    return {"daily": {
        "time": ["2026-07-19", "2026-07-26"],
        "weather_code": [95, 0],
        "temperature_2m_max": [22.5, 24.1],
        "temperature_2m_min": [17.4, 17.3],
        "precipitation_sum": [17.7, 0.0],
        "wind_speed_10m_max": [9.5, 15.0],
    }}


def test_parse_forecast_maps_codes_and_advice():
    days = w.parse_forecast(_payload())
    assert len(days) == 2
    storm, clear = days
    assert storm.date == "2026-07-19" and storm.condition == "гроза"
    assert storm.outdoor_ok is False
    assert clear.condition == "ясно" and clear.outdoor_ok is True


def test_parse_forecast_tolerates_nulls_and_short_arrays():
    payload = {"daily": {"time": ["2026-07-19"], "weather_code": [None],
                         "temperature_2m_max": [], "precipitation_sum": [None]}}
    days = w.parse_forecast(payload)
    assert len(days) == 1 and days[0].code == 0


def test_parse_forecast_empty():
    assert w.parse_forecast({}) == []


# ── Геокодер: ловушка «200 без results» ───────────────────────────────
class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p


def test_geocode_missing_city_returns_none_not_crash(monkeypatch):
    """Несуществующий город → HTTP 200 БЕЗ ключа results (не 404)."""
    monkeypatch.setattr(w.httpx, "get", lambda *a, **k: FakeResp({"generationtime_ms": 0.1}))
    assert w.geocode("Ъъънесуществует") is None


def test_geocode_ok(monkeypatch):
    payload = {"results": [{"latitude": 57.15, "longitude": 65.52,
                            "timezone": "Asia/Yekaterinburg", "name": "Тюмень"}]}
    monkeypatch.setattr(w.httpx, "get", lambda *a, **k: FakeResp(payload))
    loc = w.geocode("Тюмень")
    assert loc["lat"] == 57.15 and loc["tz"] == "Asia/Yekaterinburg"


def test_geocode_empty_city():
    assert w.geocode("") is None


def test_geocode_caches_negative_result(monkeypatch):
    """Не долбить API повторно по ненайденному городу."""
    calls = []

    def fake_get(*a, **k):
        calls.append(1)
        return FakeResp({})

    monkeypatch.setattr(w.httpx, "get", fake_get)
    assert w.geocode("Нетакого") is None
    assert w.geocode("Нетакого") is None
    assert len(calls) == 1


def test_forecast_returns_empty_when_city_unknown(monkeypatch):
    monkeypatch.setattr(w.httpx, "get", lambda *a, **k: FakeResp({}))
    assert w.forecast("Нетакого") == []


def test_for_date_finds_day(monkeypatch):
    monkeypatch.setattr(w, "geocode", lambda c: {"lat": 1, "lon": 2, "tz": "UTC", "name": "X"})
    monkeypatch.setattr(w.httpx, "get", lambda *a, **k: FakeResp(_payload()))
    day = w.for_date("Тюмень", "2026-07-19")
    assert day and day.condition == "гроза" and day.outdoor_ok is False
    assert w.for_date("Тюмень", "2027-01-01") is None
