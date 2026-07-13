"""Тесты LLM-слоя: сборка запросов провайдеров и хранилище настроек (без сети)."""
from __future__ import annotations

import base64

import pytest

from agents.llm.base import ChatMessage, LLMError, split_system
from agents.llm import providers as P
from agents.llm.registry import PROVIDERS, default_config
from config.store import SettingsStore, mask_secret


MSGS = [ChatMessage("system", "Ты МЭТР"), ChatMessage("user", "Привет")]


# ── YandexGPT ────────────────────────────────────────────────────────
def test_yandex_build_ok():
    url, headers, body = P.yandex_build(
        {"api_key": "K", "folder_id": "F", "model": "yandexgpt/latest"}, MSGS, 0.5, 200)
    assert headers["Authorization"] == "Api-Key K"
    assert headers["x-folder-id"] == "F"
    assert body["modelUri"] == "gpt://F/yandexgpt/latest"
    assert body["messages"][1] == {"role": "user", "text": "Привет"}


def test_yandex_requires_key():
    with pytest.raises(LLMError):
        P.yandex_build({"folder_id": "F"}, MSGS, 0.5, 200)


def test_yandex_parse():
    data = {"result": {"alternatives": [{"message": {"text": "готово"}}]}}
    assert P.yandex_parse(data) == "готово"


# ── GigaChat ─────────────────────────────────────────────────────────
def test_gigachat_oauth_build():
    url, headers, data = P.gigachat_oauth_build({"authorization_key": "QQ==", "scope": "GIGACHAT_API_PERS"})
    assert headers["Authorization"] == "Basic QQ=="
    assert "RqUID" in headers and len(headers["RqUID"]) >= 32
    assert data == {"scope": "GIGACHAT_API_PERS"}


def test_gigachat_chat_build_and_parse():
    url, headers, body = P.gigachat_chat_build({"model": "GigaChat"}, "TOK", MSGS, 0.6, 300)
    assert headers["Authorization"] == "Bearer TOK"
    assert body["messages"][0] == {"role": "system", "content": "Ты МЭТР"}
    assert P.gigachat_parse({"choices": [{"message": {"content": "ответ"}}]}) == "ответ"


# ── OpenAI-совместимый ───────────────────────────────────────────────
def test_openai_build_default_base():
    url, headers, body = P.openai_build({"api_key": "sk"}, MSGS, 0.5, 100)
    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk"
    assert body["model"] == "gpt-4o-mini"


def test_openai_custom_base_trailing_slash():
    url, _, _ = P.openai_build({"api_key": "sk", "base_url": "https://api.deepseek.com/"}, MSGS, 0.5, 100)
    assert url == "https://api.deepseek.com/chat/completions"


# ── Claude ───────────────────────────────────────────────────────────
def test_claude_build_splits_system():
    url, headers, body = P.claude_build({"api_key": "sk-ant"}, MSGS, 0.5, 100)
    assert headers["x-api-key"] == "sk-ant"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == "Ты МЭТР"                 # system вынесен отдельно
    assert all(m["role"] != "system" for m in body["messages"])


def test_claude_parse():
    assert P.claude_parse({"content": [{"text": "hi"}]}) == "hi"


def test_split_system_helper():
    system, rest = split_system(MSGS)
    assert system == "Ты МЭТР"
    assert len(rest) == 1


# ── Реестр ───────────────────────────────────────────────────────────
def test_registry_has_named_providers():
    keys = {p["key"] for p in PROVIDERS}
    assert {"yandexgpt", "gigachat", "openai", "claude"} <= keys
    for p in PROVIDERS:
        assert p["fields"], f"{p['key']} без полей"


def test_default_config_picks_defaults():
    assert default_config("openai")["base_url"] == "https://api.openai.com/v1"


# ── Хранилище настроек ───────────────────────────────────────────────
def test_store_masks_and_keeps_secret(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    store.update("yandexgpt", {"yandexgpt": {"api_key": "SECRET123", "folder_id": "F1"}})
    cfg = store.get_provider_config("yandexgpt")
    assert cfg["api_key"] == "SECRET123"
    assert store.active_provider() == "yandexgpt"

    # пустой секрет не затирает сохранённый ключ
    store.update(None, {"yandexgpt": {"api_key": "", "folder_id": "F2"}})
    cfg = store.get_provider_config("yandexgpt")
    assert cfg["api_key"] == "SECRET123"      # ключ сохранился
    assert cfg["folder_id"] == "F2"           # несекретное поле обновилось


def test_mask_secret():
    assert mask_secret("")["set"] is False
    m = mask_secret("abcd1234")
    assert m["set"] is True and m["hint"] == "…1234"


def test_ui_settings_hides_raw_key(tmp_path, monkeypatch):
    # ui_settings берёт глобальный store; подменим его на временный
    from config import store as store_mod
    from agents.llm import service as svc
    tmp = SettingsStore(tmp_path / "s.json")
    tmp.update("openai", {"openai": {"api_key": "sk-topsecret", "model": "gpt-4o"}})
    monkeypatch.setattr(store_mod, "store", tmp)
    monkeypatch.setattr(svc, "store", tmp)
    ui = svc.ui_settings()
    prov = {p["key"]: p for p in ui["providers"]}["openai"]
    assert prov["values"]["api_key"]["set"] is True
    assert "sk-topsecret" not in str(ui)       # сырой ключ не утёк в ответ
    assert prov["values"]["model"] == "gpt-4o"
