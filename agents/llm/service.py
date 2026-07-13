"""Высокоуровневый сервис LLM: выбор провайдера, вызовы, проверка связи,
готовые сценарии МЭТРА (ответ на отзыв, вечерняя сводка).
"""
from __future__ import annotations

import logging

from config.store import store, SECRET_FIELDS, mask_secret
from .base import ChatMessage, LLMError
from .providers import PROVIDER_CLASSES
from .registry import PROVIDERS, PROVIDER_BY_KEY, default_config

log = logging.getLogger("restopulse.llm")

# Системная роль МЭТРА — задаёт голос бренда для всех генераций
MAITRE_SYSTEM = (
    "Ты — МЭТР, цифровой метрдотель премиального ресторана. Говоришь по-русски, "
    "от первого лица, безукоризненно вежливо и сдержанно, с лёгким холодком "
    "профессионала старой школы. Никогда не суетишься, не льстишь, не "
    "извиняешься без причины. Не используешь восклицательные знаки, эмодзи, "
    "канцелярит и маркетинговый тон. Пишешь кратко и по делу."
)


def _merged_config(key: str) -> dict:
    cfg = default_config(key)
    cfg.update(store.get_provider_config(key))
    return cfg


def get_provider(key: str | None = None):
    """Возвращает экземпляр провайдера. По умолчанию — активный из настроек."""
    key = key or store.active_provider()
    if not key:
        raise LLMError("Не выбран активный AI-ассистент. Задайте его в настройках.")
    cls = PROVIDER_CLASSES.get(key)
    if not cls:
        raise LLMError(f"Неизвестный провайдер: {key}")
    return cls(_merged_config(key))


def chat(messages: list[ChatMessage], *, key: str | None = None,
         temperature: float = 0.6, max_tokens: int = 800) -> str:
    return get_provider(key).chat(messages, temperature=temperature, max_tokens=max_tokens).text


def test_connection(key: str) -> dict:
    """Короткий реальный вызов для проверки ключей. Возвращает {ok, message}."""
    try:
        text = get_provider(key).chat(
            [ChatMessage("user", "Ответь одним словом: работает")],
            temperature=0.0, max_tokens=16)
        return {"ok": True, "message": f"Связь есть. Ответ: {text.strip()[:80]}"}
    except LLMError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:  # сетевые/прочие
        return {"ok": False, "message": f"Ошибка соединения: {exc}"}


# ── Готовые сценарии МЭТРА ────────────────────────────────────────────
TONES = {
    "warm": "тепло и по-человечески, но сдержанно",
    "formal": "официально и максимально нейтрально",
    "apologetic": "с достоинством признавая проблему, без самоуничижения",
}


def maitre_reply(review_text: str, *, tone: str = "warm", key: str | None = None) -> str:
    """Черновик ответа на отзыв гостя в голосе МЭТРА."""
    review_text = (review_text or "").strip()
    if not review_text:
        raise LLMError("Пустой текст отзыва")
    tone_desc = TONES.get(tone, TONES["warm"])
    prompt = (
        f"Гость оставил отзыв о ресторане:\n\n«{review_text}»\n\n"
        f"Напиши короткий ответ от лица ресторана — {tone_desc}. "
        "2–4 предложения. Обратись к сути отзыва, поблагодари, при негативе — "
        "предложи решение. Без шаблонных фраз и штампов. Только текст ответа."
    )
    return chat([ChatMessage("system", MAITRE_SYSTEM), ChatMessage("user", prompt)],
                key=key, temperature=0.7, max_tokens=400)


def maitre_digest_note(context: str, *, key: str | None = None) -> str:
    """Вечерняя сводка МЭТРА по краткому контексту анализа (голос бренда)."""
    prompt = (
        "На основе данных ниже напиши вечернюю сводку владельцу в своём стиле: "
        "приветствие, один-два ключевых факта, рекомендация со сроком (например «до конца недели»), "
        "и в конце — человеческая деталь. Без списков, сплошным абзацем, 3–5 предложений.\n\n"
        f"Данные:\n{context}"
    )
    return chat([ChatMessage("system", MAITRE_SYSTEM), ChatMessage("user", prompt)],
                key=key, temperature=0.6, max_tokens=500)


# ── Данные для UI настроек ────────────────────────────────────────────
def ui_settings() -> dict:
    """Конфиг для страницы настроек: метаданные + текущие значения
    (секреты замаскированы)."""
    active = store.active_provider()
    out_providers = []
    for meta in PROVIDERS:
        pkey = meta["key"]
        stored = store.get_provider_config(pkey)
        secret = SECRET_FIELDS.get(pkey, set())
        values = {}
        for f in meta["fields"]:
            name = f["name"]
            if name in secret:
                values[name] = mask_secret(stored.get(name, ""))
            else:
                values[name] = stored.get(name, f.get("default", ""))
        out_providers.append({**meta, "values": values})
    return {"active_provider": active, "providers": out_providers}


def apply_settings(active_provider: str | None, providers_patch: dict) -> None:
    if active_provider and active_provider not in PROVIDER_BY_KEY:
        raise LLMError(f"Неизвестный провайдер: {active_provider}")
    store.update(active_provider, providers_patch)
