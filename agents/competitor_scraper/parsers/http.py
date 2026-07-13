"""Общий HTTP-клиент для парсеров: вежливый краулинг.

Задаёт User-Agent, таймаут, паузу между запросами, ретраи с
экспоненциальной задержкой и проверку robots.txt. Никакого агрессивного
параллельного краулинга — запросы идут последовательно с задержкой.
"""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

from config.settings import settings

log = logging.getLogger("restopulse.http")

# Кэш robots.txt по хосту, чтобы не тянуть его на каждый запрос
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def _robots_for(url: str) -> urllib.robotparser.RobotFileParser | None:
    """Возвращает разобранный robots.txt для хоста url (с кэшем).
    При ошибке загрузки возвращает None — тогда считаем, что доступ разрешён."""
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    if host in _robots_cache:
        return _robots_cache[host]
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{host}/robots.txt")
    try:
        rp.read()
    except Exception as exc:  # сеть/парсинг robots — не критично
        log.debug("robots.txt недоступен для %s: %s", host, exc)
        _robots_cache[host] = None  # type: ignore[assignment]
        return None
    _robots_cache[host] = rp
    return rp


def allowed_by_robots(url: str) -> bool:
    """Разрешает ли robots.txt нашему User-Agent запрашивать url."""
    rp = _robots_for(url)
    if rp is None:
        return True
    try:
        return rp.can_fetch(settings.http_user_agent, url)
    except Exception:
        return True


def get(url: str, *, params: dict | None = None, retries: int = 2, respect_robots: bool = True) -> httpx.Response | None:
    """Вежливый GET: robots.txt → пауза → запрос с ретраями.

    Возвращает Response при успехе (2xx) или None — если запрещено robots,
    исчерпаны ретраи или сервер отдал ошибку. None означает «данных нет»,
    а не «выдумай данные».
    """
    if respect_robots and not allowed_by_robots(url):
        log.warning("robots.txt запрещает доступ: %s", url)
        return None

    headers = {
        "User-Agent": settings.http_user_agent,
        "Accept-Language": "ru,en;q=0.8",
    }
    delay = settings.request_delay_sec
    for attempt in range(retries + 1):
        # Пауза перед запросом — уважение к источнику
        time.sleep(delay)
        try:
            resp = httpx.get(
                url,
                params=params,
                headers=headers,
                timeout=settings.request_timeout_sec,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            log.warning("HTTP-ошибка (%s/%s) %s: %s", attempt + 1, retries + 1, url, exc)
            delay *= 2  # экспоненциальная задержка
            continue
        if resp.status_code == 200:
            return resp
        if resp.status_code in (403, 429):
            # Похоже на блокировку/лимит — уходим с экспоненциальной задержкой
            log.warning("Код %s (%s/%s) %s", resp.status_code, attempt + 1, retries + 1, url)
            delay *= 2
            continue
        log.warning("Код %s для %s", resp.status_code, url)
        return None
    return None
