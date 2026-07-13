"""Тесты агента модерации (rule-based, без сети)."""
from __future__ import annotations

from agents.moderation import rules
from agents.moderation.rules import BLOCK, WARN
from agents.moderation import service as mod


def codes(issues, level=None):
    return {i.code for i in issues if level is None or i.level == level}


# ── Ценовое давление → block ─────────────────────────────────────────
def test_discount_blocked():
    for text in ["Скидка 20% на всё меню!", "Успей на распродажу", "Промокод NUAR", "Акция для гостей"]:
        r = mod.moderate(text)
        assert r.level == BLOCK, text
        assert not r.ok


def test_percent_blocked():
    r = mod.moderate("Только сегодня -30% на горячее")
    assert not r.ok and "price" in codes(r.issues, BLOCK)


def test_clean_premium_post_ok():
    text = ("В пятницу у нас джазовый вечер. Живая музыка, приглушённый свет и "
            "особое сезонное меню от шефа. Столик у сцены стоит забронировать заранее.")
    r = mod.moderate(text)
    assert r.ok and r.level == "ok" and r.issues == []


# ── Мягкие замечания → warn (не блокируют) ───────────────────────────
def test_emoji_warns_not_blocks():
    r = mod.moderate("Ждём вас на ужин \U0001F609 будет уютно и по-домашнему тепло")
    assert r.ok                       # публиковать можно
    assert "emoji" in codes(r.issues, WARN)


def test_exclaim_and_caps_warn():
    r = mod.moderate("СРОЧНО приходите!! Будет очень интересно и вкусно, ждём всех гостей")
    assert r.ok
    assert "exclaim" in codes(r.issues, WARN)
    assert "caps" in codes(r.issues, WARN)


def test_too_short_warn():
    r = mod.moderate("Ждём вас")
    assert "too_short" in codes(r.issues, WARN)


def test_empty_blocked():
    r = mod.moderate("   ")
    assert not r.ok and "empty" in codes(r.issues, BLOCK)


# ── Лимит длины под сеть ─────────────────────────────────────────────
def test_telegram_length_limit_blocks():
    long = "а" * 5000
    assert not mod.moderate(long, "telegram").ok            # > 4096
    assert mod.moderate(long, "vk").ok                      # в пределах лимита VK


# ── Результат сериализуется для API ──────────────────────────────────
def test_result_to_dict():
    d = mod.moderate("Скидка 50%").to_dict()
    assert d["ok"] is False and d["level"] == "block"
    assert d["issues"] and "level" in d["issues"][0] and "message" in d["issues"][0]


# ── Публикация блокируется модерацией ────────────────────────────────
def test_publish_blocked_by_moderation(tmp_path, monkeypatch):
    from agents.content import service, store as store_mod
    from agents.content.models import Post
    from agents.content.store import ContentStore
    st = ContentStore(tmp_path / "c.json")
    monkeypatch.setattr(store_mod, "store", st)
    monkeypatch.setattr(service, "content_store", st)
    st.upsert(Post(id="p", network="vk", text="Скидка 30% для всех", status="approved", created_at="x"))

    called = {"published": False}
    import agents.publishers.vk as vkmod
    monkeypatch.setattr(vkmod, "publish", lambda text, cfg=None: called.__setitem__("published", True))

    try:
        service.publish_post("p")
        assert False, "должно было заблокироваться"
    except mod.ModerationError as e:
        assert e.result.level == BLOCK
    assert called["published"] is False        # публикатор не вызывался
