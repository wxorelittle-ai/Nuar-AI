"""Общий HTTP-клиент для публикаторов.

Две задачи:
  • принудительный IPv4 (local_address="0.0.0.0") — часть провайдеров режут
    Telegram только по IPv6, поэтому IPv4-путь иногда живёт;
  • опциональный прокси — единственный чисто-серверный способ обойти
    egress-блокировку Telegram, когда путь к api.telegram.org закрыт совсем.

Прокси и локальный адрес совмещаются в одном транспорте: соединение до
прокси идёт по IPv4, дальше прокси сам достаёт заблокированный хост.
"""
from __future__ import annotations

import httpx

from config.settings import settings


def make_client(proxy: str | None = None) -> httpx.Client:
    """httpx.Client с IPv4-транспортом и, если задан, прокси.

    proxy — URL прокси (http/https/socks5) или пусто/None. Пустая строка
    трактуется как «без прокси».
    """
    proxy = (proxy or "").strip()
    kwargs = {"local_address": "0.0.0.0"}
    if proxy:
        kwargs["proxy"] = proxy
    transport = httpx.HTTPTransport(**kwargs)
    return httpx.Client(timeout=settings.request_timeout_sec, transport=transport)
