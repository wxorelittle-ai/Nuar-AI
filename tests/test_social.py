"""Тесты анализа соцсетей конкурентов (VK) — без сети."""
from __future__ import annotations

from agents.social import vk
from agents.social.models import PostStat


# ── Разбор домена ────────────────────────────────────────────────────
def test_extract_domain():
    assert vk.extract_domain("https://vk.com/nuarrest") == "nuarrest"
    assert vk.extract_domain("vk.com/club123?x=1") == "club123"
    assert vk.extract_domain("@nuarrest") == "nuarrest"
    assert vk.extract_domain("nuarrest") == "nuarrest"


# ── Парсинг стены ────────────────────────────────────────────────────
WALL = {
    "count": 5,
    "items": [
        {"id": 10, "owner_id": -1, "text": "Живая музыка в пятницу вечером", "date": 1_752_000_000,
         "likes": {"count": 50}, "comments": {"count": 4}, "views": {"count": 2000}},
        {"id": 9, "owner_id": -1, "text": "Новое сезонное меню от шефа", "date": 1_751_500_000,
         "likes": {"count": 30}, "comments": {"count": 2}, "views": {"count": 1500}},
        {"id": 8, "owner_id": -1, "text": "Живая музыка снова с нами", "date": 1_751_000_000,
         "likes": {"count": 90}, "comments": {"count": 10}, "views": {"count": 3000}},
        {"id": 1, "owner_id": -1, "text": "Закреплённый пост", "date": 1_700_000_000,
         "is_pinned": 1, "likes": {"count": 999}, "comments": {"count": 0}, "views": {"count": 1}},
    ],
}


def test_parse_wall_skips_pinned():
    posts = vk.parse_wall(WALL)
    assert len(posts) == 3                       # закреплённый исключён
    assert posts[0].likes == 50 and posts[0].owner_id == -1


def test_top_words_ignores_stopwords_and_short():
    posts = vk.parse_wall(WALL)
    words = {w["word"] for w in vk.top_words(posts)}
    assert "живая" in words and "музыка" in words   # повторяющиеся темы
    assert "в" not in words and "с" not in words     # стоп/короткие отброшены


def test_analytics_aggregates():
    posts = vk.parse_wall(WALL)
    a = vk.analytics("test", posts, subscribers=5000)
    assert a.ok and a.posts_analyzed == 3
    assert a.subscribers == 5000
    assert a.avg_likes == round((50 + 30 + 90) / 3, 1)
    assert a.avg_views == round((2000 + 1500 + 3000) / 3, 1)
    # ER = avg_likes / avg_views * 100
    assert a.engagement_rate > 0
    # топ-пост — с 90 лайками
    assert a.top_posts[0]["likes"] == 90
    assert a.top_posts[0]["link"].startswith("https://vk.com/wall-1_")


def test_analytics_weekday_distribution():
    posts = vk.parse_wall(WALL)
    a = vk.analytics("test", posts)
    assert sum(a.by_weekday) == 3
    assert a.best_weekday in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def test_analytics_empty():
    a = vk.analytics("test", [])
    assert not a.ok and a.error


def test_posts_per_week():
    # два поста с разницей в 7 дней → ~1 пост/неделю... проверим формулу
    posts = [PostStat(id="1", owner_id=-1, date=1_000_000, likes=1),
             PostStat(id="2", owner_id=-1, date=1_000_000 + 14 * 86400, likes=1)]
    a = vk.analytics("t", posts)
    # 2 поста за 14 дней → 1.0 в неделю
    assert a.posts_per_week == 1.0
    assert a.span_days == 14.0
