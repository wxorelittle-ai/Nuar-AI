"""Тесты гео-сравнения трендов: мир vs рус. аудитория."""
from __future__ import annotations

from agents.trends import geo
from agents.trends.models import GEO_TOPICS, TopicTrend


# ── Классификация ─────────────────────────────────────────────────────
def test_classify_coming_is_world_up_ru_not():
    assert geo.classify("up", "flat") == "coming"
    assert geo.classify("up", "down") == "coming"


def test_classify_here_when_both_up():
    assert geo.classify("up", "up") == "here"


def test_classify_local_when_only_ru_up():
    assert geo.classify("flat", "up") == "local"
    assert geo.classify("down", "up") == "local"


def test_classify_fading_when_both_down():
    assert geo.classify("down", "down") == "fading"


def test_classify_flat_otherwise():
    assert geo.classify("flat", "flat") == "flat"
    assert geo.classify("down", "flat") == "flat"


# ── Ранжирование ──────────────────────────────────────────────────────
def test_rank_puts_coming_first_and_drops_failed():
    trends = [
        geo.GeoTrend(topic="A", ok=True, verdict="fading", world_growth=-30),
        geo.GeoTrend(topic="B", ok=True, verdict="coming", world_growth=20),
        geo.GeoTrend(topic="C", ok=True, verdict="here", world_growth=50),
        geo.GeoTrend(topic="D", ok=False, verdict="flat"),
        geo.GeoTrend(topic="E", ok=True, verdict="coming", world_growth=60),
    ]
    ranked = geo.rank(trends)
    assert [t.topic for t in ranked] == ["E", "B", "C", "A"]   # coming вперёд, внутри — по росту
    assert "D" not in [t.topic for t in ranked]                # без данных — отброшен


# ── Сборка через заглушку сети ────────────────────────────────────────
def test_compare_builds_verdicts(monkeypatch):
    def fake_fetch(title, start, end, project="ru.wikipedia"):
        # мир растёт, у нас — нет; трафика достаточно
        if project == "en.wikipedia":
            return TopicTrend(topic=title, ok=True, growth=40.0, direction="up",
                              prior_avg=100.0, recent_avg=140.0, spark=[1, 2, 3])
        return TopicTrend(topic=title, ok=True, growth=2.0, direction="flat",
                          prior_avg=50.0, recent_avg=51.0, spark=[1, 1, 1])

    monkeypatch.setattr(geo.wikipedia, "fetch_topic", fake_fetch)
    out = geo.compare([("Негрони", "Негрони", "Negroni")], "20260515", "20260714")
    assert len(out) == 1
    t = out[0]
    assert t.ok and t.verdict == "coming"
    assert t.world_growth == 40.0 and t.ru_growth == 2.0
    assert "первыми" in t.note
    assert t.to_dict()["verdict_label"] == "едет к нам"


def test_compare_marks_missing_data(monkeypatch):
    def fake_fetch(title, start, end, project="ru.wikipedia"):
        if project == "en.wikipedia":
            return TopicTrend(topic=title, ok=True, growth=10.0, direction="flat",
                              prior_avg=80.0, recent_avg=88.0)
        return TopicTrend(topic=title, ok=False, error="нет статьи")

    monkeypatch.setattr(geo.wikipedia, "fetch_topic", fake_fetch)
    out = geo.compare([("Нечто", "Нечто", "Something")], "20260515", "20260714")
    assert out[0].ok is False and "нет данных" in out[0].note


# ── Порог достоверности ───────────────────────────────────────────────
def test_low_traffic_topic_is_not_trusted(monkeypatch):
    """+30% на 2 просмотрах в день — шум, а не тренд."""
    def fake_fetch(title, start, end, project="ru.wikipedia"):
        if project == "en.wikipedia":
            return TopicTrend(topic=title, ok=True, growth=30.0, direction="up",
                              prior_avg=200.0, recent_avg=260.0)
        return TopicTrend(topic=title, ok=True, growth=30.0, direction="up",
                          prior_avg=1.5, recent_avg=2.0)      # крохи трафика

    monkeypatch.setattr(geo.wikipedia, "fetch_topic", fake_fetch)
    out = geo.compare([("Негрони", "Негрони", "Negroni")], "20260515", "20260714")
    assert out[0].ok is False and "мало трафика" in out[0].note


def test_has_volume_threshold():
    assert geo.has_volume(TopicTrend(topic="x", prior_avg=2.0, recent_avg=12.0)) is True
    assert geo.has_volume(TopicTrend(topic="x", prior_avg=9.0, recent_avg=1.0)) is False


# ── Темы ──────────────────────────────────────────────────────────────
def test_geo_topics_are_triples_and_unique():
    assert len(GEO_TOPICS) >= 20
    for t in GEO_TOPICS:
        assert len(t) == 3 and all(isinstance(x, str) and x for x in t)
    labels = [label for label, ru, en in GEO_TOPICS]
    assert len(labels) == len(set(labels)), "подписи не должны повторяться"
    arts = [ru for label, ru, en in GEO_TOPICS]
    assert len(arts) == len(set(arts)), "статьи ru не должны повторяться"


def test_geo_topics_use_canonical_not_redirects():
    """Редиректы дают крохи трафика — в списке должны быть канонические статьи."""
    ru_articles = {ru for label, ru, en in GEO_TOPICS}
    for redirect in ("Матча", "Комбуча", "Фильм нуар"):
        assert redirect not in ru_articles, f"{redirect} — редирект, нужен канон"
    assert {"Маття", "Чайный гриб", "Нуар"} <= ru_articles


def test_service_analyze_geo_shape(monkeypatch):
    from agents.trends import service

    def fake_fetch(title, start, end, project="ru.wikipedia"):
        return TopicTrend(topic=title, ok=True, growth=30.0 if project == "en.wikipedia" else 1.0,
                          direction="up" if project == "en.wikipedia" else "flat",
                          prior_avg=100.0, recent_avg=120.0, spark=[1, 2])

    monkeypatch.setattr(geo.wikipedia, "fetch_topic", fake_fetch)
    data = service.analyze_geo()
    assert data["trends"] and data["coming"]
    assert all(t["verdict"] == "coming" for t in data["coming"])
    assert "en.wikipedia" in data["notice"]
