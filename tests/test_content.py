"""Тесты контент-агента и публикаторов (без сети)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from agents.publishers import vk, telegram
from agents.publishers.base import PublishError
from agents.content.models import Post, DRAFT, APPROVED, PUBLISHED
from agents.content.store import ContentStore


# ── VK publisher ─────────────────────────────────────────────────────
def test_vk_build_request():
    url, params, gid = vk.build_request({"access_token": "T", "group_id": "123"}, "привет")
    assert params["owner_id"] == "-123"       # для сообщества отрицательный id
    assert params["from_group"] == 1
    assert params["message"] == "привет"
    assert params["access_token"] == "T"
    assert gid == "123"


def test_vk_build_strips_minus_in_group_id():
    _, params, gid = vk.build_request({"access_token": "T", "group_id": "-123"}, "x")
    assert params["owner_id"] == "-123" and gid == "123"


def test_vk_requires_token_and_group():
    with pytest.raises(PublishError):
        vk.build_request({"group_id": "1"}, "x")
    with pytest.raises(PublishError):
        vk.build_request({"access_token": "T"}, "x")


def test_vk_parse_success_link():
    res = vk.parse_response({"response": {"post_id": 55}}, "123")
    assert res.ok and res.external_id == "55"
    assert res.link == "https://vk.com/wall-123_55"


def test_vk_parse_error():
    res = vk.parse_response({"error": {"error_msg": "Access denied"}}, "123")
    assert not res.ok and "Access denied" in res.error


# ── Telegram publisher ───────────────────────────────────────────────
def test_tg_build_request():
    url, payload, ch = telegram.build_request({"bot_token": "B", "channel": "@rest"}, "текст")
    assert url.endswith("/botB/sendMessage")
    assert payload["chat_id"] == "@rest" and payload["text"] == "текст"


def test_tg_requires_token_and_channel():
    with pytest.raises(PublishError):
        telegram.build_request({"channel": "@x"}, "t")
    with pytest.raises(PublishError):
        telegram.build_request({"bot_token": "B"}, "t")


def test_tg_parse_success_link_for_username():
    res = telegram.parse_response({"ok": True, "result": {"message_id": 7}}, "@rest")
    assert res.ok and res.link == "https://t.me/rest/7"


def test_tg_parse_error():
    res = telegram.parse_response({"ok": False, "description": "chat not found"}, "@rest")
    assert not res.ok and "chat not found" in res.error


# ── Post model ───────────────────────────────────────────────────────
def test_post_roundtrip_and_labels():
    p = Post(id="a1", network="telegram", content_line="Живая музыка", text="t", status=APPROVED)
    d = p.to_dict()
    assert d["network_label"] == "Telegram"
    assert d["status_label"] == "Утверждён"
    assert Post.from_dict(d).id == "a1"


# ── Content store ────────────────────────────────────────────────────
def test_content_store_upsert_get_delete(tmp_path):
    st = ContentStore(tmp_path / "c.json")
    st.upsert(Post(id="p1", text="раз", created_at="2026-07-10T10:00:00"))
    st.upsert(Post(id="p2", text="два", created_at="2026-07-11T10:00:00"))
    assert len(st.list()) == 2
    assert st.list()[0].id == "p2"            # свежие сверху
    st.upsert(Post(id="p1", text="обновлён", created_at="2026-07-10T10:00:00"))
    assert st.get("p1").text == "обновлён"
    assert st.delete("p1") and st.get("p1") is None
    assert st.delete("nope") is False


# ── Автопубликация по расписанию ─────────────────────────────────────
def test_auto_publish_due_selects_only_due_approved(tmp_path, monkeypatch):
    from agents.content import service, store as store_mod
    st = ContentStore(tmp_path / "c.json")
    monkeypatch.setattr(store_mod, "store", st)
    monkeypatch.setattr(service, "content_store", st)

    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    past = (now - timedelta(hours=1)).isoformat()
    future = (now + timedelta(hours=1)).isoformat()
    st.upsert(Post(id="due", status=APPROVED, text="a", scheduled_at=past, created_at=past))
    st.upsert(Post(id="later", status=APPROVED, text="b", scheduled_at=future, created_at=past))
    st.upsert(Post(id="draft", status=DRAFT, text="c", scheduled_at=past, created_at=past))

    published = []
    monkeypatch.setattr(service, "publish_post", lambda pid: published.append(pid) or Post(id=pid))
    service.auto_publish_due(now=now)
    assert published == ["due"]                # только наступивший и утверждённый
