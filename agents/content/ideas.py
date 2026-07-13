"""Идеи для постов из сигналов разведки + evergreen-заготовки.

Замыкает петлю «мониторинг → идея → пост»: наблюдения по конкурентам
(активность в VK, упоминания в СМИ) превращаются в темы постов-ответов, плюс
всегда добавляются базовые идеи по контент-линиям бренда.

Чистые функции — тестируются без сети. latest_ideas() дополнительно читает
последние снимки конкурентов из репозитория (если разведка уже запускалась).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict

log = logging.getLogger("restopulse.content.ideas")


@dataclass
class ContentIdea:
    content_line: str
    network: str
    topic: str
    rationale: str          # почему это стоит опубликовать
    source: str = ""        # источник (конкурент) или "" для evergreen
    weight: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("weight", None)
        return d


# Базовые идеи по контент-линиям (есть всегда)
SEEDS = [
    ("Живая музыка", "Афиша ближайшего музыкального вечера",
     "Живая музыка — ваше главное УТП. Напомните гостям о ближайшем выступлении."),
    ("Кухня и шеф", "Сезонное блюдо от шефа: история и подача",
     "Показать кухню и процесс — это укрепляет премиальное восприятие."),
    ("Атмосфера", "Вечерний зал: детали, ради которых возвращаются",
     "Атмосфера продаёт возвращения. Покажите вечерний свет и детали интерьера."),
    ("Событийность", "Анонс особого вечера или гастро-ужина",
     "Событие даёт повод прийти именно на этой неделе."),
    ("Гость", "История гостя или отзыв, которым гордитесь",
     "Социальное доказательство от лица довольных гостей."),
]


def seed_ideas(network: str = "vk") -> list[ContentIdea]:
    return [ContentIdea(cl, network, topic, why, source="", weight=10)
            for cl, topic, why in SEEDS]


def responsive_ideas(observations: list[dict], network: str = "vk") -> list[ContentIdea]:
    """Идеи-ответы на сигналы конкурентов.

    observations — список dict: {competitor, kind, ...}
      kind="vk_active" → поле n (число постов за неделю)
      kind="media"     → поле title (заголовок упоминания)
    """
    out: list[ContentIdea] = []
    for o in observations:
        name = o.get("competitor", "конкурент")
        if o.get("kind") == "vk_active":
            n = o.get("n", "")
            out.append(ContentIdea(
                "Событийность", network,
                "Ответный инфоповод: анонс вечера с живой музыкой",
                f"«{name}» активно постит в VK ({n} за неделю) — не отдавайте инфоповод, ответьте своим событием.",
                source=name, weight=100))
        elif o.get("kind") == "media":
            title = (o.get("title") or "").strip()
            out.append(ContentIdea(
                "Событийность", network,
                "Свой повод для городских СМИ",
                f"«{name}» засветился в СМИ: «{title[:60]}». Подготовьте собственный информационный повод.",
                source=name, weight=90))
    return out


def build_ideas(observations: list[dict], network: str = "vk") -> list[ContentIdea]:
    """Отклик на конкурентов + базовые идеи, с дедупликацией и ранжированием."""
    ideas = responsive_ideas(observations, network) + seed_ideas(network)
    seen: dict[tuple[str, str], ContentIdea] = {}
    for idea in ideas:
        k = (idea.content_line, idea.topic)
        if k not in seen or idea.weight > seen[k].weight:
            seen[k] = idea
    return sorted(seen.values(), key=lambda i: i.weight, reverse=True)


def _observations_from_repo() -> list[dict]:
    """Собирает наблюдения из последних снимков конкурентов (best-effort)."""
    try:
        from config.settings import load_competitors_config
        from db.repository import get_repository
        cfg = load_competitors_config()
        repo = get_repository()
        obs: list[dict] = []
        for c in cfg.get("competitors", []):
            name = c.get("name")
            if not name:
                continue
            snap = repo.latest(name)
            if snap is None:
                continue
            vk = snap.sources.get("vk")
            if vk and vk.ok and (vk.posts_last_week or 0) >= 3:
                obs.append({"competitor": name, "kind": "vk_active", "n": vk.posts_last_week})
            for m in snap.media_mentions:
                obs.append({"competitor": name, "kind": "media", "title": m.get("title", "")})
        return obs
    except Exception as exc:  # разведка ещё не запускалась / нет данных
        log.debug("Наблюдения из репозитория недоступны: %s", exc)
        return []


def latest_ideas(network: str = "vk") -> list[dict]:
    """Итоговый список идей для UI."""
    obs = _observations_from_repo()
    return [i.to_dict() for i in build_ideas(obs, network)]
