"""Сервис трендов: динамика тем + идеи контента/меню."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta

from . import wikipedia
from .models import DEFAULT_TOPICS

log = logging.getLogger("restopulse.trends")

WINDOW_DAYS = 60
LAG_DAYS = 2            # у Wikipedia данные отстают на пару дней
REQUEST_PAUSE = 0.25


def _date_range(today) -> tuple[str, str]:
    end = today - timedelta(days=LAG_DAYS)
    start = end - timedelta(days=WINDOW_DAYS)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def analyze(topics: list[str] | None = None, today=None) -> dict:
    topics = [t.strip() for t in (topics or DEFAULT_TOPICS) if t.strip()]
    today = today or datetime.now(timezone.utc).date()
    start, end = _date_range(today)

    results = []
    for i, topic in enumerate(topics):
        if i:
            time.sleep(REQUEST_PAUSE)
        results.append(wikipedia.fetch_topic(topic, start, end))

    ok = [r for r in results if r.ok]
    rising = sorted([r for r in ok if r.direction == "up"], key=lambda r: r.growth, reverse=True)
    falling = sorted([r for r in ok if r.direction == "down"], key=lambda r: r.growth)
    stable = [r for r in ok if r.direction == "flat"]
    skipped = [r.topic for r in results if not r.ok]

    return {
        "window_days": WINDOW_DAYS,
        "rising": [r.to_dict() for r in rising],
        "falling": [r.to_dict() for r in falling],
        "stable": [r.to_dict() for r in stable],
        "skipped": skipped,
        "suggestions": _suggestions(rising),
        "notice": _notice(ok, skipped),
    }


def _suggestions(rising: list) -> list[dict]:
    out = []
    for r in rising[:3]:
        out.append({
            "topic": r.topic,
            "text": f"«{r.topic}» набирает интерес (+{r.growth}%). Обыграйте тему: пост-анонс "
                    f"или сезонная позиция/спецвечер вокруг «{r.topic}».",
        })
    return out


def _notice(ok: list, skipped: list) -> str:
    if not ok:
        return ("Не удалось получить данные трендов. Проверьте темы (названия статей Wikipedia) "
                "или повторите позже.")
    base = "Данные Wikipedia Pageviews — прокси интереса за ~2 месяца."
    if skipped:
        base += f" Пропущено (нет статьи/данных): {', '.join(skipped)}."
    return base


def default_topics() -> list[str]:
    return list(DEFAULT_TOPICS)
