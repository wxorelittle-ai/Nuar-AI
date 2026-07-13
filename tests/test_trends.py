"""Тесты трендов: разбор ряда и вычисление направления (без сети)."""
from __future__ import annotations

from agents.trends import wikipedia
from agents.trends.service import _date_range
from datetime import date


def test_build_url_encodes_title():
    url = wikipedia.build_url("Том-ям", "20260101", "20260301")
    assert "ru.wikipedia" in url and "daily/20260101/20260301" in url
    assert "%D0%A2" in url          # кириллица URL-энкодится
    assert " " not in url


def test_parse_series():
    data = {"items": [{"views": 10}, {"views": 20}, {"views": 0}]}
    assert wikipedia.parse_series(data) == [10, 20, 0]


def test_trend_rising():
    # первая половина низкая, вторая высокая → up
    views = [10] * 15 + [40] * 15
    t = wikipedia.trend_from_series(views)
    assert t["ok"] and t["direction"] == "up"
    assert t["growth"] > 15
    assert len(t["spark"]) > 0


def test_trend_falling():
    views = [50] * 15 + [10] * 15
    t = wikipedia.trend_from_series(views)
    assert t["direction"] == "down" and t["growth"] < -15


def test_trend_flat():
    views = [30] * 30
    t = wikipedia.trend_from_series(views)
    assert t["direction"] == "flat"


def test_trend_insufficient_data():
    t = wikipedia.trend_from_series([1, 2, 3])
    assert not t["ok"]


def test_date_range_shape():
    start, end = _date_range(date(2026, 7, 13))
    assert len(start) == 8 and len(end) == 8
    assert end <= "20260713"          # с учётом лага end < сегодня
