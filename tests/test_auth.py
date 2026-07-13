"""Тесты авторизации и повторных попыток публикации."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from web import auth


def _set_password(monkeypatch, pw):
    monkeypatch.setattr(auth, "settings", SimpleNamespace(admin_password=pw, secret_key=""))


@pytest.fixture
def secret(tmp_path, monkeypatch):
    # фиксированный секрет, чтобы токены были детерминированы
    monkeypatch.setattr(auth, "_secret", lambda: b"test-secret-key")
    return b"test-secret-key"


def test_token_roundtrip(secret):
    tok = auth.make_token()
    assert auth.valid_token(tok)


def test_token_tampered_rejected(secret):
    tok = auth.make_token()
    exp, sig = tok.split(".", 1)
    assert not auth.valid_token(f"{exp}.{sig}x")     # подделка подписи
    assert not auth.valid_token("garbage")
    assert not auth.valid_token(None)


def test_token_expired_rejected(secret, monkeypatch):
    tok = auth.make_token()
    monkeypatch.setattr(auth.time, "time", lambda: 9_999_999_999)  # далёкое будущее
    assert not auth.valid_token(tok)


def test_auth_disabled_when_no_password(monkeypatch):
    _set_password(monkeypatch, "")
    assert auth.auth_enabled() is False
    # is_authed True при выключенной авторизации
    class Req: cookies = {}
    assert auth.is_authed(Req()) is True


def test_check_password(monkeypatch):
    _set_password(monkeypatch, "s3cret")
    assert auth.check_password("s3cret") is True
    assert auth.check_password("wrong") is False
    assert auth.check_password("") is False


def test_is_authed_requires_valid_cookie(secret, monkeypatch):
    _set_password(monkeypatch, "s3cret")
    good = auth.make_token()

    class Req:
        def __init__(self, c): self.cookies = c

    assert auth.is_authed(Req({auth.COOKIE: good})) is True
    assert auth.is_authed(Req({})) is False
    assert auth.is_authed(Req({auth.COOKIE: "bad"})) is False


# ── Повторные попытки автопубликации ─────────────────────────────────
def test_autopublish_retries_then_fails(tmp_path, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from agents.content import service, store as store_mod
    from agents.content.models import Post, APPROVED, FAILED
    from agents.content.store import ContentStore

    st = ContentStore(tmp_path / "c.json")
    monkeypatch.setattr(store_mod, "store", st)
    monkeypatch.setattr(service, "content_store", st)

    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    past = (now - timedelta(minutes=1)).isoformat()
    st.upsert(Post(id="p", network="vk", text="Спокойный премиальный пост про ужин",
                   status=APPROVED, scheduled_at=past, created_at=past))

    # публикация всегда падает (сеть недоступна) — publish_post вернёт пост с error, не PUBLISHED
    def failing_publish(pid, **kw):
        p = st.get(pid); p.error = "VK: ошибка сети"; st.upsert(p); return p
    monkeypatch.setattr(service, "publish_post", failing_publish)

    for _ in range(3):
        service.auto_publish_due(now=now)

    p = st.get("p")
    assert p.attempts == 3
    assert p.status == FAILED         # после лимита попыток — «Ошибка»
