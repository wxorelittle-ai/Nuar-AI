"""Публикаторы: сборка запросов и выбор прокси (без реальной сети)."""
from __future__ import annotations

import httpx
import pytest

from agents.publishers import telegram, vk
from agents.publishers.http import make_client


def test_make_client_no_proxy():
    with make_client("") as c:
        assert isinstance(c, httpx.Client)


def test_make_client_with_proxy():
    # не ходит в сеть, лишь конструирует транспорт с прокси
    with make_client("http://127.0.0.1:1080") as c:
        assert isinstance(c, httpx.Client)


def test_telegram_uses_cfg_proxy(monkeypatch):
    """proxy из конфигурации канала передаётся в make_client."""
    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"ok": True, "result": {"message_id": 7}}

    class FakeClient:
        def __init__(self, proxy):
            captured["proxy"] = proxy
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, json=None):
            return FakeResp()

    monkeypatch.setattr(telegram, "make_client", lambda proxy=None: FakeClient(proxy))
    res = telegram.publish("привет", {"bot_token": "T", "channel": "@c", "proxy": "socks5://p:9050"})
    assert res.ok
    assert captured["proxy"] == "socks5://p:9050"


def test_telegram_falls_back_to_env_proxy(monkeypatch):
    """если в канале прокси не задан — берётся settings.telegram_proxy."""
    import types
    captured = {}
    monkeypatch.setattr(telegram, "settings", types.SimpleNamespace(telegram_proxy="http://envproxy:3128"))

    class FakeClient:
        def __init__(self, proxy):
            captured["proxy"] = proxy
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, json=None):
            class R:
                status_code = 200
                def json(self_inner):
                    return {"ok": True, "result": {"message_id": 1}}
            return R()

    monkeypatch.setattr(telegram, "make_client", lambda proxy=None: FakeClient(proxy))
    telegram.publish("x", {"bot_token": "T", "channel": "@c"})
    assert captured["proxy"] == "http://envproxy:3128"


def test_vk_build_request_owner_id_negative():
    url, params, gid = vk.build_request({"access_token": "tok", "group_id": "123"}, "текст")
    assert params["owner_id"] == "-123"
    assert params["from_group"] == 1
    assert gid == "123"


def test_vk_missing_token_errors():
    res = vk.publish("t", {"group_id": "1"})
    assert not res.ok and "access_token" in res.error


# ── check() ──────────────────────────────────────────────────────────

def _fake_client(status, payload, capture=None):
    class R:
        status_code = status
        def json(self):
            return payload
    class C:
        def __init__(self, proxy=None):
            if capture is not None:
                capture["proxy"] = proxy
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, url):
            return R()
        def post(self, url, data=None):
            return R()
    return C


def test_telegram_check_ok(monkeypatch):
    cap = {}
    monkeypatch.setattr(telegram, "make_client",
                        lambda proxy=None: _fake_client(200, {"ok": True, "result": {"username": "mybot"}}, cap)(proxy))
    res = telegram.check({"bot_token": "T", "channel": "@c", "proxy": "http://p:3128"})
    assert res.ok and res.external_id == "mybot"
    assert cap["proxy"] == "http://p:3128"


def test_telegram_check_no_token():
    res = telegram.check({"channel": "@c"})
    assert not res.ok and "токен" in res.error


def test_vk_check_ok(monkeypatch):
    monkeypatch.setattr(vk, "make_client",
                        lambda proxy=None: _fake_client(200, {"response": {"groups": [{"name": "Моё кафе"}]}})(proxy))
    res = vk.check({"access_token": "tok", "group_id": "123"})
    assert res.ok and res.external_id == "Моё кафе"
    assert res.link == "https://vk.com/club123"


def test_vk_check_api_error(monkeypatch):
    monkeypatch.setattr(vk, "make_client",
                        lambda proxy=None: _fake_client(200, {"error": {"error_msg": "invalid token"}})(proxy))
    res = vk.check({"access_token": "bad", "group_id": "1"})
    assert not res.ok and "invalid token" in res.error


def test_service_test_channel_unknown():
    from agents.content import service
    assert service.test_channel("unknown")["ok"] is False
