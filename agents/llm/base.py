"""Базовые типы LLM-слоя."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str      # system | user | assistant
    content: str


@dataclass
class LLMResult:
    text: str
    raw: dict | None = None


class LLMError(Exception):
    """Понятная пользователю ошибка вызова ассистента."""


def split_system(messages: list[ChatMessage]) -> tuple[str, list[ChatMessage]]:
    """Отделяет системные сообщения (для API, где system идёт отдельно, — Claude)."""
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    rest = [m for m in messages if m.role != "system"]
    return system, rest
