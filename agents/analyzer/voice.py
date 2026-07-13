"""Голос МЭТРА (rule-based): вечерняя сводка по результату анализа.

Работает всегда, без LLM. Структура — как в бренд-гайде: приветствие → факт →
рекомендация со сроком → человеческая деталь в конце. Названия конкурентов
оборачиваются в <em> (курсив-антиква на фронте).
"""
from __future__ import annotations

from .models import RestaurantProfile, Strategy


def _fmt_dist(m):
    if m is None:
        return "нескольких минутах"
    return f"{m} метрах" if m < 1000 else f"{m/1000:.1f} км"


def maitre_note(profile: RestaurantProfile, strategy: Strategy) -> str:
    parts = ["Добрый вечер."]

    if strategy.top_threats:
        t = strategy.top_threats[0]
        if t.rating is not None:
            parts.append(f"По соседству <em>«{t.name}»</em> — {t.rating} в {_fmt_dist(t.distance_m)}, "
                         "прямой конкурент за вашего гостя.")

    # Дыра по отзывам между площадками
    ok = [p for p in profile.platforms if p.ok and p.reviews_count is not None]
    gap = None
    if len(ok) >= 2:
        strong = max(ok, key=lambda p: p.reviews_count)
        weak = min(ok, key=lambda p: p.reviews_count)
        if strong.reviews_count >= 5 * max(weak.reviews_count, 1):
            gap = (weak.platform, weak.reviews_count, strong.platform, strong.reviews_count)

    if gap:
        parts.append(f"Слабое место одно: на {gap[0]} всего {gap[1]} отзыва против {gap[3]} на {gap[2]} — "
                     "рекомендую закрыть этот разрыв до конца недели.")
    elif strategy.priorities:
        parts.append(f"До конца недели советую заняться одним: {strategy.priorities[0].title.lower()}.")

    yr, avg = strategy.your_rating, strategy.avg_competitor_rating
    if yr is not None and avg is not None and yr > avg:
        parts.append("Рейтинг у вас выше среднего по округе — его нужно показать там, где вас пока не видят.")
    else:
        parts.append("Я наблюдаю за округой и вернусь с новой сводкой в понедельник.")

    return " ".join(parts)
