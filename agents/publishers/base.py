"""Базовые типы публикаторов."""
from __future__ import annotations

from dataclasses import dataclass


class PublishError(Exception):
    """Понятная пользователю ошибка публикации."""


@dataclass
class PublishResult:
    ok: bool
    link: str = ""          # ссылка на опубликованный пост
    external_id: str = ""   # id поста в сети
    error: str = ""
