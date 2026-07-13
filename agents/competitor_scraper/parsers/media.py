"""Поиск упоминаний конкурентов в городских СМИ (1tmn.ru, nashgorod.ru).

Делает поисковый запрос по имени конкурента на каждом медиа и вытаскивает
заголовки+ссылки результатов. Это best-effort: разметка выдачи у СМИ разная и
меняется, поэтому берём широкой эвристикой (ссылки с текстом, содержащим имя
конкурента) и не падаем, если ничего не нашли.
"""
from __future__ import annotations

import logging
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from .http import get

log = logging.getLogger("restopulse.parser.media")

# Сколько упоминаний максимум берём с одного источника
MAX_HITS_PER_SOURCE = 3


def search(competitor_name: str, media_sources: list[dict]) -> list[dict]:
    """Возвращает список упоминаний: [{source, title, url}].

    media_sources — записи из competitors.yaml (name, search_url с {query})."""
    mentions: list[dict] = []
    name_lower = competitor_name.lower()

    for src in media_sources:
        search_url = src.get("search_url", "")
        if "{query}" not in search_url:
            continue
        url = search_url.replace("{query}", quote_plus(competitor_name))
        resp = get(url)
        if resp is None:
            log.debug("СМИ %s недоступно для запроса %s", src.get("name"), competitor_name)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            if len(title) < 15:  # отсекаем меню/навигацию
                continue
            if name_lower not in title.lower():
                continue
            href = urljoin(url, a["href"])
            if href in seen:
                continue
            seen.add(href)
            mentions.append({"source": src.get("name", ""), "title": title[:200], "url": href})
            if len(seen) >= MAX_HITS_PER_SOURCE:
                break

    return mentions
