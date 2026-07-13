"""Адаптеры провайдеров LLM.

Каждый адаптер: чистые builder/parse-функции (тестируются без сети) + класс
провайдера, который делает HTTP. Все ошибки → LLMError с понятным текстом.
"""
from __future__ import annotations

import uuid

import httpx

from config.settings import settings
from .base import ChatMessage, LLMResult, LLMError, split_system

TIMEOUT = 60


def _client(verify: bool = True) -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, verify=verify)


# ══════════════════════════════════════════════════════════════════════
# YandexGPT — Yandex Cloud Foundation Models
# ══════════════════════════════════════════════════════════════════════
YANDEX_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


def yandex_build(cfg: dict, messages: list[ChatMessage], temperature: float, max_tokens: int):
    api_key = cfg.get("api_key")
    folder_id = cfg.get("folder_id")
    model = cfg.get("model") or "yandexgpt-lite/latest"
    if not api_key:
        raise LLMError("YandexGPT: не задан API-ключ")
    if not folder_id:
        raise LLMError("YandexGPT: не задан Folder ID (идентификатор каталога)")
    headers = {"Authorization": f"Api-Key {api_key}", "x-folder-id": folder_id,
               "Content-Type": "application/json"}
    body = {
        "modelUri": f"gpt://{folder_id}/{model}",
        "completionOptions": {"stream": False, "temperature": temperature, "maxTokens": str(max_tokens)},
        "messages": [{"role": m.role, "text": m.content} for m in messages],
    }
    return YANDEX_URL, headers, body


def yandex_parse(data: dict) -> str:
    try:
        return data["result"]["alternatives"][0]["message"]["text"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("YandexGPT: неожиданный ответ API")


class YandexGPTProvider:
    key, title = "yandexgpt", "YandexGPT"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def chat(self, messages, *, temperature=0.6, max_tokens=800) -> LLMResult:
        url, headers, body = yandex_build(self.cfg, messages, temperature, max_tokens)
        with _client() as c:
            r = c.post(url, headers=headers, json=body)
        if r.status_code != 200:
            raise LLMError(f"YandexGPT: HTTP {r.status_code} — {r.text[:200]}")
        return LLMResult(text=yandex_parse(r.json()), raw=r.json())


# ══════════════════════════════════════════════════════════════════════
# GigaChat — Sber. Двухшаговая авторизация (OAuth → chat).
# ══════════════════════════════════════════════════════════════════════
GIGACHAT_OAUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_CHAT = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


def gigachat_oauth_build(cfg: dict):
    auth = cfg.get("authorization_key")
    scope = cfg.get("scope") or "GIGACHAT_API_PERS"
    if not auth:
        raise LLMError("GigaChat: не задан Authorization key (Base64 client_id:secret)")
    headers = {
        "Authorization": f"Basic {auth}",
        "RqUID": str(uuid.uuid4()),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    return GIGACHAT_OAUTH, headers, {"scope": scope}


def gigachat_chat_build(cfg: dict, token: str, messages: list[ChatMessage], temperature: float, max_tokens: int):
    model = cfg.get("model") or "GigaChat"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return GIGACHAT_CHAT, headers, body


def gigachat_parse(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("GigaChat: неожиданный ответ API")


class GigaChatProvider:
    key, title = "gigachat", "GigaChat"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        # GigaChat использует корневой сертификат Минцифры РФ. Если он не
        # установлен в системе — временно можно отключить проверку SSL.
        self.verify = bool(self.cfg.get("verify_ssl", False))

    def _token(self, client: httpx.Client) -> str:
        url, headers, data = gigachat_oauth_build(self.cfg)
        r = client.post(url, headers=headers, data=data)
        if r.status_code != 200:
            raise LLMError(f"GigaChat: авторизация не удалась — HTTP {r.status_code} {r.text[:160]}")
        token = r.json().get("access_token")
        if not token:
            raise LLMError("GigaChat: сервер не вернул access_token")
        return token

    def chat(self, messages, *, temperature=0.6, max_tokens=800) -> LLMResult:
        with _client(verify=self.verify) as c:
            token = self._token(c)
            url, headers, body = gigachat_chat_build(self.cfg, token, messages, temperature, max_tokens)
            r = c.post(url, headers=headers, json=body)
        if r.status_code != 200:
            raise LLMError(f"GigaChat: HTTP {r.status_code} — {r.text[:200]}")
        return LLMResult(text=gigachat_parse(r.json()), raw=r.json())


# ══════════════════════════════════════════════════════════════════════
# OpenAI-совместимый (OpenAI, DeepSeek, OpenRouter, локальные серверы)
# ══════════════════════════════════════════════════════════════════════
def openai_build(cfg: dict, messages: list[ChatMessage], temperature: float, max_tokens: int):
    api_key = cfg.get("api_key")
    base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = cfg.get("model") or "gpt-4o-mini"
    if not api_key:
        raise LLMError("OpenAI-совместимый: не задан API-ключ")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    return f"{base}/chat/completions", headers, body


def openai_parse(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("OpenAI-совместимый: неожиданный ответ API")


class OpenAICompatProvider:
    key, title = "openai", "OpenAI-совместимый"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def chat(self, messages, *, temperature=0.6, max_tokens=800) -> LLMResult:
        url, headers, body = openai_build(self.cfg, messages, temperature, max_tokens)
        with _client() as c:
            r = c.post(url, headers=headers, json=body)
        if r.status_code != 200:
            raise LLMError(f"OpenAI-совместимый: HTTP {r.status_code} — {r.text[:200]}")
        return LLMResult(text=openai_parse(r.json()), raw=r.json())


# ══════════════════════════════════════════════════════════════════════
# Claude — Anthropic Messages API
# ══════════════════════════════════════════════════════════════════════
CLAUDE_URL = "https://api.anthropic.com/v1/messages"


def claude_build(cfg: dict, messages: list[ChatMessage], temperature: float, max_tokens: int):
    api_key = cfg.get("api_key")
    model = cfg.get("model") or "claude-3-5-sonnet-latest"
    if not api_key:
        raise LLMError("Claude: не задан API-ключ")
    system, rest = split_system(messages)
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": m.role, "content": m.content} for m in rest],
    }
    if system:
        body["system"] = system
    return CLAUDE_URL, headers, body


def claude_parse(data: dict) -> str:
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("Claude: неожиданный ответ API")


class ClaudeProvider:
    key, title = "claude", "Claude"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def chat(self, messages, *, temperature=0.6, max_tokens=800) -> LLMResult:
        url, headers, body = claude_build(self.cfg, messages, temperature, max_tokens)
        with _client() as c:
            r = c.post(url, headers=headers, json=body)
        if r.status_code != 200:
            raise LLMError(f"Claude: HTTP {r.status_code} — {r.text[:200]}")
        return LLMResult(text=claude_parse(r.json()), raw=r.json())


PROVIDER_CLASSES = {
    "yandexgpt": YandexGPTProvider,
    "gigachat": GigaChatProvider,
    "openai": OpenAICompatProvider,
    "claude": ClaudeProvider,
}
