"""Тесты движка идей (разведка → контент) и repository.latest."""
from __future__ import annotations

from agents.content import ideas as ideas_mod
from agents.content.ideas import build_ideas, seed_ideas, responsive_ideas
from db.repository import JsonRepository
from models.competitor import CompetitorSnapshot, SourceSnapshot


# ── Базовые идеи ─────────────────────────────────────────────────────
def test_seed_ideas_cover_key_lines():
    ideas = seed_ideas("vk")
    lines = {i.content_line for i in ideas}
    assert {"Живая музыка", "Кухня и шеф", "Атмосфера", "Событийность"} <= lines
    assert all(i.network == "vk" for i in ideas)


# ── Идеи-ответы на конкурентов ───────────────────────────────────────
def test_responsive_from_vk_activity():
    obs = [{"competitor": "Арбат", "kind": "vk_active", "n": 5}]
    ideas = responsive_ideas(obs, "vk")
    assert len(ideas) == 1
    assert ideas[0].source == "Арбат"
    assert "Арбат" in ideas[0].rationale and "5" in ideas[0].rationale
    assert ideas[0].weight >= 100


def test_responsive_from_media():
    obs = [{"competitor": "Сыроварня", "kind": "media", "title": "Открыли летнюю веранду"}]
    ideas = responsive_ideas(obs, "telegram")
    assert ideas[0].source == "Сыроварня"
    assert "веранд" in ideas[0].rationale.lower()
    assert ideas[0].network == "telegram"


def test_build_ranks_responsive_above_seeds():
    obs = [{"competitor": "Арбат", "kind": "vk_active", "n": 4}]
    ideas = build_ideas(obs, "vk")
    assert ideas[0].source == "Арбат"          # ответные идеи выше базовых
    assert any(i.source == "" for i in ideas)  # базовые тоже присутствуют


def test_build_dedup_keeps_highest_weight():
    # два одинаковых наблюдения не должны дублировать идею
    obs = [{"competitor": "Арбат", "kind": "vk_active", "n": 4},
           {"competitor": "Арбат", "kind": "vk_active", "n": 4}]
    ideas = build_ideas(obs, "vk")
    keys = [(i.content_line, i.topic) for i in ideas]
    assert len(keys) == len(set(keys))


def test_to_dict_shape():
    d = seed_ideas("vk")[0].to_dict()
    assert set(d) == {"content_line", "network", "topic", "rationale", "source"}
    assert "weight" not in d


# ── repository.latest ────────────────────────────────────────────────
def test_repository_latest(tmp_path):
    repo = JsonRepository(tmp_path / "snap.json")
    s1 = CompetitorSnapshot("Арбат", "2026-07-01T09:00:00")
    s2 = CompetitorSnapshot("Арбат", "2026-07-08T09:00:00")
    s2.sources["vk"] = SourceSnapshot("vk", ok=True, posts_last_week=5)
    repo.save_snapshot(s1)
    repo.save_snapshot(s2)
    latest = repo.latest("Арбат")
    assert latest.collected_at == "2026-07-08T09:00:00"
    assert latest.sources["vk"].posts_last_week == 5
    assert repo.latest("Неизвестный") is None


# ── latest_ideas читает наблюдения из репозитория ────────────────────
def test_latest_ideas_uses_repo(tmp_path, monkeypatch):
    repo = JsonRepository(tmp_path / "snap.json")
    snap = CompetitorSnapshot("Арбат", "2026-07-08T09:00:00")
    snap.sources["vk"] = SourceSnapshot("vk", ok=True, posts_last_week=6)
    repo.save_snapshot(snap)

    monkeypatch.setattr("db.repository.get_repository", lambda: repo)
    monkeypatch.setattr("config.settings.load_competitors_config",
                        lambda *a, **k: {"competitors": [{"name": "Арбат"}], "media_sources": []})
    ideas = ideas_mod.latest_ideas("vk")
    assert any(i["source"] == "Арбат" for i in ideas)   # ответная идея появилась
