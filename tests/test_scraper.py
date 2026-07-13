"""Юнит-тесты: diff-логика дайджеста, модели, парсинг без сети.

Сеть не дёргаем — проверяем чистую логику сравнения снимков и рендеринг.
Запуск:  pytest
"""
from __future__ import annotations

from pathlib import Path

import pytest

from models.competitor import Competitor, CompetitorSnapshot, SourceSnapshot, Review
from models.digest import RATING, VK_ACTIVITY, IMPORTANT
from agents.competitor_scraper import digest as digest_mod
from db.repository import JsonRepository


# ── Фикстуры ─────────────────────────────────────────────────────────
def _snap(name, at, *, dgis_rating=None, dgis_reviews=None, vk_posts=None, vk_subs=None):
    s = CompetitorSnapshot(competitor_name=name, collected_at=at)
    if dgis_rating is not None:
        s.sources["dgis"] = SourceSnapshot(
            source="dgis", ok=True, rating=dgis_rating, reviews_count=dgis_reviews
        )
    if vk_posts is not None:
        s.sources["vk"] = SourceSnapshot(
            source="vk", ok=True, posts_last_week=vk_posts, subscribers=vk_subs
        )
    return s


class _StubRepo:
    """Репозиторий, всегда возвращающий заданный «прошлый» снимок."""
    def __init__(self, previous=None):
        self._prev = previous
    def latest_before(self, name, before_iso):
        return self._prev
    def save_snapshot(self, snap): ...
    def save_digest(self, *a, **k): ...


ARBAT = Competitor(name="Арбат", priority="high")


# ── Тесты diff рейтинга ──────────────────────────────────────────────
def test_rating_increase_detected():
    prev = _snap("Арбат", "2026-07-01T09:00:00", dgis_rating=4.7, dgis_reviews=95)
    cur = _snap("Арбат", "2026-07-08T09:00:00", dgis_rating=4.8, dgis_reviews=98)
    d = digest_mod.build_digest([ARBAT], {"Арбат": cur}, _StubRepo(prev),
                                "неделя", "2026-07-08T09:00:00")
    rating_changes = d.by_category(RATING)
    assert len(rating_changes) == 1
    assert "4.7 → 4.8" in rating_changes[0].text
    assert "+3 отзывов" in rating_changes[0].text


def test_rating_noise_ignored():
    # Изменение меньше порога RATING_EPS — не считаем изменением
    prev = _snap("Арбат", "2026-07-01T09:00:00", dgis_rating=4.80)
    cur = _snap("Арбат", "2026-07-08T09:00:00", dgis_rating=4.82)
    d = digest_mod.build_digest([ARBAT], {"Арбат": cur}, _StubRepo(prev),
                                "неделя", "2026-07-08T09:00:00")
    assert d.by_category(RATING) == []


def test_first_measurement_is_baseline():
    cur = _snap("Арбат", "2026-07-08T09:00:00", dgis_rating=4.7, dgis_reviews=95)
    d = digest_mod.build_digest([ARBAT], {"Арбат": cur}, _StubRepo(None),
                                "неделя", "2026-07-08T09:00:00")
    changes = d.by_category(RATING)
    assert len(changes) == 1
    assert "первый замер" in changes[0].text


# ── Тесты VK-активности ──────────────────────────────────────────────
def test_vk_activity_trend():
    prev = _snap("Арбат", "2026-07-01T09:00:00", vk_posts=2)
    cur = _snap("Арбат", "2026-07-08T09:00:00", vk_posts=5)
    d = digest_mod.build_digest([ARBAT], {"Арбат": cur}, _StubRepo(prev),
                                "неделя", "2026-07-08T09:00:00")
    vk_changes = d.by_category(VK_ACTIVITY)
    assert any("5 постов" in c.text and "↑" in c.text for c in vk_changes)


def test_high_priority_pr_spike_goes_to_important():
    cur = _snap("Арбат", "2026-07-08T09:00:00", vk_posts=4)
    d = digest_mod.build_digest([ARBAT], {"Арбат": cur}, _StubRepo(None),
                                "неделя", "2026-07-08T09:00:00")
    important = d.by_category(IMPORTANT)
    assert any("PR-кампания" in c.text for c in important)


# ── Рендеринг ────────────────────────────────────────────────────────
def test_render_contains_header_and_recommendation():
    cur = _snap("Арбат", "2026-07-08T09:00:00", dgis_rating=4.8, dgis_reviews=98)
    d = digest_mod.build_digest([ARBAT], {"Арбат": cur}, _StubRepo(None),
                                "7–13 июля 2026", "2026-07-08T09:00:00")
    text = digest_mod.render_markdown(d)
    assert "Еженедельный разведдайджест Nuar" in text
    assert "7–13 июля 2026" in text
    assert "РЕКОМЕНДАЦИЯ" in text


def test_empty_digest_has_no_changes_note():
    cur = CompetitorSnapshot(competitor_name="Арбат", collected_at="2026-07-08T09:00:00")
    d = digest_mod.build_digest([ARBAT], {"Арбат": cur}, _StubRepo(None),
                                "неделя", "2026-07-08T09:00:00")
    text = digest_mod.render_markdown(d)
    assert d.is_empty
    assert "значимых изменений" in text.lower()


# ── Модели: сериализация round-trip ──────────────────────────────────
def test_snapshot_roundtrip():
    s = _snap("Арбат", "2026-07-08T09:00:00", dgis_rating=4.8, dgis_reviews=98, vk_posts=5)
    s.sources["dgis"].recent_reviews = [Review(author="Гость", rating=5.0, text="Отлично")]
    restored = CompetitorSnapshot.from_dict(s.to_dict())
    assert restored.competitor_name == "Арбат"
    assert restored.sources["dgis"].rating == 4.8
    assert restored.sources["dgis"].recent_reviews[0].author == "Гость"
    assert restored.sources["vk"].posts_last_week == 5


# ── JSON-репозиторий: сохранение и поиск предыдущего снимка ───────────
def test_json_repo_latest_before(tmp_path: Path):
    repo = JsonRepository(tmp_path / "snap.json")
    repo.save_snapshot(_snap("Арбат", "2026-07-01T09:00:00", dgis_rating=4.7))
    repo.save_snapshot(_snap("Арбат", "2026-07-08T09:00:00", dgis_rating=4.8))
    prev = repo.latest_before("Арбат", "2026-07-08T09:00:00")
    assert prev is not None
    assert prev.sources["dgis"].rating == 4.7  # берётся именно предыдущий, не текущий


def test_config_competitors_loads():
    from config.settings import load_competitors_config
    cfg = load_competitors_config()
    names = [c["name"] for c in cfg["competitors"]]
    assert "Арбат" in names
    assert "Мята" in names
