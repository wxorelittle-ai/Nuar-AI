"""Сервис анализа соцсетей конкурентов."""
from __future__ import annotations

from . import vk


def analyze_vk(domain: str) -> dict:
    """Анализ VK-группы конкурента. Возвращает dict для UI."""
    result = vk.fetch(domain)
    data = result.to_dict()
    data["notice"] = _notice(result)
    return data


def _notice(result) -> str:
    if result.error == "не задан VK_SERVICE_TOKEN":
        return ("Для анализа VK задайте VK_SERVICE_TOKEN в .env (сервисный ключ приложения VK, "
                "dev.vk.com). Без него доступ к стене закрыт.")
    if result.error:
        return f"Не удалось собрать данные: {result.error}"
    return "Данные VK API. Метрики — по последним постам на стене сообщества."
