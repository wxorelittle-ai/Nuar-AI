"""Сравнение интереса по уровням: мир (en.wikipedia) vs рус. аудитория (ru.wikipedia).

Смысл не в самих цифрах, а в РАЗНИЦЕ между уровнями. Если тема растёт в мире,
но у нас ещё плоская — это окно: можно зайти форматом первым в городе. Если
растёт у нас — тема уже здесь, конкуренция выше.

Запросы идут параллельно (Pageviews API это выдерживает; User-Agent обязателен
по правилам Wikimedia). Чистые функции разбора тестируются без сети.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

from . import wikipedia
from .models import GEO_TOPICS

log = logging.getLogger("restopulse.trends.geo")

RU_PROJECT = "ru.wikipedia"
EN_PROJECT = "en.wikipedia"
MAX_WORKERS = 6

# Порог достоверности: на статье с 2 просмотрами в день «рост +25%» — это шум,
# а не тренд. Темы, где хоть один уровень ниже порога, помечаем как недостоверные
# и не пускаем в вердикты.
MIN_AVG_VIEWS = 10.0

# Вердикты и как их читать управляющему
VERDICTS = {
    "coming": "едет к нам",
    "here": "уже здесь",
    "local": "наша волна",
    "fading": "уходит",
    "flat": "без движения",
}


def has_volume(trend) -> bool:
    """Достаточно ли трафика, чтобы процент роста что-то значил."""
    return max(trend.recent_avg or 0.0, trend.prior_avg or 0.0) >= MIN_AVG_VIEWS


@dataclass
class GeoTrend:
    topic: str                  # подпись для UI
    topic_en: str = ""
    ok: bool = False
    world_growth: float = 0.0
    ru_growth: float = 0.0
    world_dir: str = "flat"
    ru_dir: str = "flat"
    verdict: str = "flat"
    spark: list[int] = None     # ряд мирового интереса (для мини-графика)
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["spark"] = self.spark or []
        d["verdict_label"] = VERDICTS.get(self.verdict, self.verdict)
        return d


def classify(world_dir: str, ru_dir: str) -> str:
    """Вердикт по паре направлений. Порядок проверок важен."""
    if world_dir == "up" and ru_dir != "up":
        return "coming"
    if world_dir == "up" and ru_dir == "up":
        return "here"
    if ru_dir == "up" and world_dir != "up":
        return "local"
    if world_dir == "down" and ru_dir == "down":
        return "fading"
    return "flat"


def _note(verdict: str, topic: str) -> str:
    if verdict == "coming":
        return (f"«{topic}» растёт в мире, но у нас ещё нет — окно, чтобы зайти первыми "
                f"в городе: спецпозиция или тематический вечер.")
    if verdict == "here":
        return f"«{topic}» растёт и в мире, и у нас — тема горячая, но и конкуренция выше."
    if verdict == "local":
        return f"«{topic}» растёт у нас без мировой волны — локальный интерес, можно усилить."
    if verdict == "fading":
        return f"«{topic}» теряет интерес везде — не ставить в основу вечера."
    return ""


def compare(topics: list[tuple[str, str, str]] | None, start: str, end: str) -> list[GeoTrend]:
    """Сравнивает темы по двум проектам. topics — (подпись, статья ru, статья en).

    Запросы идут параллельно.
    """
    topics = topics or GEO_TOPICS
    jobs: list[tuple[str, str, str]] = []
    for _label, ru, en in topics:
        jobs.append((RU_PROJECT, ru, "ru"))
        jobs.append((EN_PROJECT, en, "en"))

    def run(job):
        project, title, side = job
        return side, title, wikipedia.fetch_topic(title, start, end, project)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(run, jobs))

    by_side: dict[tuple[str, str], object] = {(s, t): tr for s, t, tr in results}
    out: list[GeoTrend] = []
    for label, ru, en in topics:
        r = by_side.get(("ru", ru))
        w = by_side.get(("en", en))
        if not (r and w and r.ok and w.ok):
            out.append(GeoTrend(topic=label, topic_en=en, ok=False,
                                note="нет данных по одному из уровней"))
            continue
        if not (has_volume(r) and has_volume(w)):
            out.append(GeoTrend(topic=label, topic_en=en, ok=False,
                                note="мало трафика — процент недостоверен"))
            continue
        verdict = classify(w.direction, r.direction)
        out.append(GeoTrend(
            topic=label, topic_en=en, ok=True,
            world_growth=w.growth, ru_growth=r.growth,
            world_dir=w.direction, ru_dir=r.direction,
            verdict=verdict, spark=w.spark, note=_note(verdict, label)))
    return out


# Порядок важности вердиктов для управляющего
_ORDER = {"coming": 0, "here": 1, "local": 2, "flat": 3, "fading": 4}


def rank(trends: list[GeoTrend]) -> list[GeoTrend]:
    """Сначала «едет к нам» (самый ценный сигнал), внутри — по мировому росту."""
    ok = [t for t in trends if t.ok]
    return sorted(ok, key=lambda t: (_ORDER.get(t.verdict, 9), -t.world_growth))
