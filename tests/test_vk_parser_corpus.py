"""Парсер VK должен удерживать корпус постов, а не выбрасывать 29 из 30."""
from __future__ import annotations

from types import SimpleNamespace

from agents.competitor_scraper.parsers import vk as vkp
from models.competitor import Competitor


def _settings(token: str) -> SimpleNamespace:
    # settings — frozen dataclass, поэтому подменяем объект целиком
    return SimpleNamespace(vk_service_token=token, vk_api_version="5.199")


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _wall(n: int, now_ts: int) -> dict:
    return {"response": {"items": [
        {"id": i, "date": now_ts - i * 3600, "text": f"пост номер {i}"} for i in range(n)]}}


def test_parser_keeps_post_corpus(monkeypatch):
    now = 1_800_000_000

    def fake_get(url, params=None, **kw):
        if "groups.getById" in url:
            return FakeResp({"response": {"groups": [{"members_count": 500}]}})
        return FakeResp(_wall(30, now))

    monkeypatch.setattr(vkp, "get", fake_get)
    monkeypatch.setattr(vkp, "settings", _settings("TOKEN"))

    snap = vkp.fetch(Competitor(name="X", vk_domain="x"), now_ts=now)
    assert snap.ok
    assert len(snap.recent_post_texts) == 30, "корпус должен сохраняться целиком"
    assert snap.recent_post_texts[0] == "пост номер 0"      # самый свежий первым
    assert snap.latest_post_text == "пост номер 0"


def test_parser_caps_corpus_and_skips_empty(monkeypatch):
    now = 1_800_000_000
    items = [{"id": i, "date": now - i, "text": ""} for i in range(5)]
    items += [{"id": 100 + i, "date": now - 100 - i, "text": f"текст {i}"} for i in range(40)]

    def fake_get(url, params=None, **kw):
        if "groups.getById" in url:
            return FakeResp({"response": {"groups": [{"members_count": 1}]}})
        return FakeResp({"response": {"items": items}})

    monkeypatch.setattr(vkp, "get", fake_get)
    monkeypatch.setattr(vkp, "settings", _settings("TOKEN"))

    snap = vkp.fetch(Competitor(name="X", vk_domain="x"), now_ts=now)
    assert len(snap.recent_post_texts) == vkp.MAX_POSTS_KEPT
    assert all(t.strip() for t in snap.recent_post_texts), "пустые посты в корпус не берём"


def test_no_token_gives_no_corpus(monkeypatch):
    monkeypatch.setattr(vkp, "settings", _settings(""))
    snap = vkp.fetch(Competitor(name="X", vk_domain="x"), now_ts=1)
    assert not snap.ok and snap.recent_post_texts == []
    assert "VK_SERVICE_TOKEN" in snap.error
