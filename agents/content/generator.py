"""Генерация постов через активный AI-ассистент.

Пишет пост для соцсети премиального ресторана в фирменном тоне (без скидок,
ценового давления и канцелярита). Учитывает особенности сети: VK — можно
развёрнуто, Telegram — компактнее.
"""
from __future__ import annotations

from agents.llm.base import ChatMessage, LLMError
from agents.llm import service as llm

SYSTEM = (
    "Ты — контент-редактор премиального ресторана. Пишешь посты для соцсетей "
    "живо, но со вкусом и достоинством. Премиальная аудитория: НИКАКИХ скидок, "
    "акций и ценового давления, никакого канцелярита и кликбейта. Тон спокойный, "
    "уверенный. Без эмодзи и без обилия восклицательных знаков."
)

NET_HINT = {
    "vk": "Сеть — ВКонтакте: можно 3–6 предложений, допустимы 2–3 тематических хэштега в конце.",
    "telegram": "Сеть — Telegram-канал: компактно, 2–4 предложения, без хэштегов.",
}


def generate_post(*, network: str, content_line: str, topic: str = "",
                  restaurant: str = "", tone: str = "", key: str | None = None) -> str:
    """Возвращает текст поста. Требует настроенного активного ассистента."""
    net_hint = NET_HINT.get(network, NET_HINT["vk"])
    lines = [f"Ресторан: {restaurant}." if restaurant else "",
             f"Контент-линия: {content_line}." if content_line else "",
             f"Тема/повод: {topic}." if topic else "",
             f"Дополнительно: {tone}." if tone else "",
             net_hint,
             "Напиши готовый текст поста. Только текст, без пояснений и заголовков вроде «Пост:»."]
    prompt = "\n".join(l for l in lines if l)
    return llm.chat([ChatMessage("system", SYSTEM), ChatMessage("user", prompt)],
                    key=key, temperature=0.8, max_tokens=600).strip()
