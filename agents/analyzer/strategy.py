"""Стратегический движок: из профиля + конкурентов строит SWOT, приоритеты,
контент-план и карту угроз.

Правила data-driven: чем больше реальных данных (рейтинги, отзывы, дистанции),
тем конкретнее выводы. Там, где данных нет, движок не выдумывает цифры, а даёт
сегментные рекомендации и честно помечает пробелы.
"""
from __future__ import annotations

from statistics import mean

from .models import (
    RestaurantProfile, NearbyCompetitor, Strategy,
    SwotItem, Priority, ContentLine, SEGMENTS,
)

# Пороги оценки
STRONG_RATING = 4.6          # выше — сильный сигнал качества
WEAK_RATING = 4.3            # ниже у конкурента — шанс перетока гостей
NEAR_METERS = 400            # ближе — «прямой сосед»
LOW_REVIEWS = 15             # меньше отзывов на площадке — площадка не работает
REVIEW_GAP_RATIO = 5         # во столько раз одна площадка обгоняет другую → дыра


def _positioning(profile: RestaurantProfile, rank: int | None, total: int | None) -> str:
    seg = SEGMENTS.get(profile.segment, "заведение")
    r = profile.best_rating
    place = ""
    if rank and total:
        place = f" Позиция по рейтингу в округе: {rank} из {total}."
    if r is None:
        return (f"{profile.name} — {seg.lower()} в городе {profile.city}. "
                f"Пока нет подтверждённых данных по рейтингу — первый шаг закрыть площадки.{place}")
    if r >= STRONG_RATING:
        return (f"{profile.name} — сильный {seg.lower()} (рейтинг {r}). "
                f"Задача — конвертировать репутацию в поток и удержание.{place}")
    return (f"{profile.name} — {seg.lower()} с рейтингом {r}. "
            f"Есть зона роста качества/сервиса до уровня лидеров округа.{place}")


def _review_gap(profile: RestaurantProfile) -> tuple[str, int] | None:
    """Ищет площадку-дыру: где отзывов кратно меньше, чем на другой."""
    ok = [p for p in profile.platforms if p.ok and p.reviews_count is not None]
    if len(ok) < 2:
        return None
    strong = max(ok, key=lambda p: p.reviews_count)
    weak = min(ok, key=lambda p: p.reviews_count)
    if strong.reviews_count >= REVIEW_GAP_RATIO * max(weak.reviews_count, 1):
        return weak.platform, weak.reviews_count
    return None


def build_strategy(profile: RestaurantProfile, competitors: list[NearbyCompetitor]) -> Strategy:
    s = Strategy()

    rated = [c for c in competitors if c.rating is not None]
    your_r = profile.best_rating
    s.your_rating = your_r

    # ── Позиция в округе ─────────────────────────────────────────────
    if rated:
        s.avg_competitor_rating = round(mean(c.rating for c in rated), 2)
        if your_r is not None:
            board = sorted([your_r] + [c.rating for c in rated], reverse=True)
            s.rank = board.index(your_r) + 1
            s.total_places = len(board)

    s.positioning = _positioning(profile, s.rank, s.total_places)

    # ── SWOT ─────────────────────────────────────────────────────────
    # Сильные стороны
    if your_r is not None and your_r >= STRONG_RATING:
        s.strengths.append(SwotItem(f"Высокий рейтинг {your_r}", "Сильный сигнал качества для новых гостей"))
    if s.avg_competitor_rating and your_r and your_r > s.avg_competitor_rating:
        s.strengths.append(SwotItem(
            f"Рейтинг выше среднего по округе (+{round(your_r - s.avg_competitor_rating, 2)})",
            f"Средний по конкурентам — {s.avg_competitor_rating}"))
    top_platform = max((p for p in profile.platforms if p.ok and p.reviews_count),
                       key=lambda p: p.reviews_count, default=None)
    if top_platform and (top_platform.reviews_count or 0) >= LOW_REVIEWS * 3:
        s.strengths.append(SwotItem(
            f"Накоплена база отзывов на {top_platform.platform} ({top_platform.reviews_count})",
            "Социальное доказательство уже работает на привлечение"))
    if not s.strengths:
        s.strengths.append(SwotItem("Данных для явных сильных сторон мало",
                                    "Закройте площадки и соберите отзывы — сильные стороны проявятся в цифрах"))

    # Слабые стороны
    gap = _review_gap(profile)
    if gap:
        s.weaknesses.append(SwotItem(
            f"Критическая дыра: на {gap[0]} всего {gap[1]} отзывов",
            "Площадка почти не работает на вас — теряете видимость в поиске по картам"))
    missing = [p.platform for p in profile.platforms if not p.ok]
    if missing:
        s.weaknesses.append(SwotItem(
            f"Нет данных по площадкам: {', '.join(missing)}",
            "Карточка не заполнена или не найдена — гости вас там не видят"))
    if s.avg_competitor_rating and your_r and your_r < s.avg_competitor_rating:
        s.weaknesses.append(SwotItem(
            f"Рейтинг ниже среднего по округе (−{round(s.avg_competitor_rating - your_r, 2)})",
            "Конкуренты выглядят предпочтительнее при выборе"))
    if not s.weaknesses:
        s.weaknesses.append(SwotItem("Явных слабых мест по данным не видно",
                                     "Держите ритм работы с отзывами и контентом"))

    # Возможности
    weak_rivals = [c for c in rated if c.rating is not None and c.rating < WEAK_RATING]
    if weak_rivals:
        names = ", ".join(c.name for c in weak_rivals[:3])
        s.opportunities.append(SwotItem(
            f"Рядом конкуренты со слабым рейтингом: {names}",
            "Недовольные их гости — ваша целевая аудитория для перетока"))
    if gap or missing:
        s.opportunities.append(SwotItem(
            "Незакрытые площадки = быстрый рост видимости",
            "Заполнение карточки и сбор отзывов дают приток почти без затрат"))
    if profile.segment == "fine_dining":
        s.opportunities.append(SwotItem(
            "Премиум-сегмент: работа с VIP-базой и событийностью",
            "Персональные приглашения и особые вечера конкуренты не копируют быстро"))
    if not s.opportunities:
        s.opportunities.append(SwotItem("Усиление контента и удержания",
                                        "Регулярный качественный контент + возврат гостей"))

    # Угрозы + карта угроз
    threats_scored: list[tuple[float, NearbyCompetitor, str]] = []
    for c in rated:
        score = 0.0
        reasons = []
        if c.rating is not None and c.rating >= STRONG_RATING:
            score += c.rating
            reasons.append(f"рейтинг {c.rating}")
        if c.distance_m is not None and c.distance_m <= NEAR_METERS:
            score += 2
            reasons.append(f"{c.distance_m} м")
        if your_r is not None and c.rating is not None and c.rating > your_r:
            score += 1
            reasons.append("рейтинг выше вашего")
        if score > 0:
            threats_scored.append((score, c, ", ".join(reasons)))
    threats_scored.sort(key=lambda t: t[0], reverse=True)
    s.top_threats = [c for _, c, _ in threats_scored[:3]]
    for _, c, reason in threats_scored[:3]:
        s.threats.append(SwotItem(f"{c.name}", reason))
    if not s.threats:
        s.threats.append(SwotItem("Сильных прямых угроз рядом не выявлено",
                                   "Следите за динамикой конкурентов еженедельно"))

    # ── Приоритеты (quick wins), ранжируем по weight ─────────────────
    prio: list[Priority] = []
    if gap:
        prio.append(Priority(
            f"Закрыть дыру на {gap[0]}",
            f"Сейчас там {gap[1]} отзывов. Мотивируйте гостей оставлять отзывы именно на этой площадке — быстрый рост видимости.",
            effort="низкий", impact="высокий", weight=100))
    if missing:
        prio.append(Priority(
            "Заполнить/подтвердить карточки на картах",
            f"Нет данных по: {', '.join(missing)}. Заведите и верифицируйте карточку — без этого нет поискового трафика с карт.",
            effort="низкий", impact="высокий", weight=95))
    prio.append(Priority(
        "Настроить работу с отзывами",
        "Отвечать на каждый отзыв (черновик готовит система, публикует человек) — это поднимает рейтинг и лояльность.",
        effort="средний", impact="высокий", weight=80))
    if your_r is not None and s.avg_competitor_rating and your_r < s.avg_competitor_rating:
        prio.append(Priority(
            "Аудит сервиса и качества",
            "Рейтинг ниже среднего по округе — разберите свежие негативные отзывы, найдите системные причины.",
            effort="высокий", impact="высокий", weight=85))
    if profile.segment == "fine_dining":
        prio.append(Priority(
            "Запустить VIP-удержание",
            "Персональные сценарии для постоянных гостей (день рождения, «давно не было») — без скидок, от лица управляющего.",
            effort="средний", impact="высокий", weight=70))
    prio.append(Priority(
        "Контент-ритм 2–3 поста в неделю",
        "Регулярный качественный контент по линиям ниже вместо потока ради частоты.",
        effort="средний", impact="средний", weight=50))
    prio.sort(key=lambda p: p.weight, reverse=True)
    s.priorities = prio

    # ── Контент-линии по сегменту ────────────────────────────────────
    s.content_lines = _content_lines(profile.segment)

    return s


def _content_lines(segment: str) -> list[ContentLine]:
    base = [
        ContentLine("Кухня и шеф", "Процесс, сезонные позиции, история блюда, знакомство с командой"),
        ContentLine("Атмосфера", "Вечерний зал, детали интерьера, гости (с разрешения)"),
        ContentLine("Событийность", "Анонсы особых вечеров, гастро-ужинов, коллабораций"),
        ContentLine("Гость", "Отзывы, истории, повод вернуться"),
    ]
    if segment == "fine_dining":
        base.insert(0, ContentLine("Живая музыка / особые вечера",
                                   "Афиши, видео выступлений, знакомство с артистами — то, что не копируется быстро"))
    if segment == "bar":
        base.insert(0, ContentLine("Барная карта и бармены",
                                   "Авторские коктейли, сеты, барный чемпионат, лица за стойкой"))
    if segment == "cafe":
        base.insert(0, ContentLine("Кофе и завтраки",
                                   "Обжарка, сезонные напитки, утренние сеты, уют"))
    return base
