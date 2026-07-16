"""Тесты окон возможностей: какие форматы не встречаются у конкурентов."""
from __future__ import annotations

from agents.competitor_scraper import gaps
from models.competitor import CompetitorSnapshot, SourceSnapshot


def _snap(name: str, texts: list[str], ok: bool = True) -> CompetitorSnapshot:
    s = CompetitorSnapshot(competitor_name=name, collected_at="2026-07-16T00:00:00")
    vk = SourceSnapshot(source="vk", ok=ok)
    vk.recent_post_texts = texts
    s.sources["vk"] = vk
    return s


# ── Разметка форматов ─────────────────────────────────────────────────
def test_detect_formats_basic():
    assert "Джаз и блюз" in gaps.detect_formats("В пятницу — джазовый вечер")
    assert "Караоке" in gaps.detect_formats("Караоке до утра")
    assert "Квиз и игры" in gaps.detect_formats("Приходите на квиз")


def test_detect_formats_is_case_and_yo_insensitive():
    assert "Живая музыка" in gaps.detect_formats("ЖИВАЯ МУЗЫКА каждый вечер")
    # «ё» не должна ломать поиск
    assert gaps.detect_formats("Живая музыка") == gaps.detect_formats("Живая музыка")


def test_detect_formats_multiple_in_one_text():
    found = gaps.detect_formats("Джаз-вечер и дегустация виски, потом караоке")
    assert {"Джаз и блюз", "Дегустация", "Караоке"} <= found


def test_detect_formats_empty():
    assert gaps.detect_formats("") == set()
    assert gaps.detect_formats("Просто хороший вечер у нас") == set()


# ── Отчёт ─────────────────────────────────────────────────────────────
def test_analyze_marks_occupied_and_free():
    texts_a = ["Джазовый вечер"] * 6
    texts_b = ["Квиз в четверг"] * 6
    rep = gaps.analyze([_snap("A", texts_a), _snap("B", texts_b)])
    assert rep.posts_analyzed == 12
    names = [o["name"] for o in rep.occupied]
    assert "Джаз и блюз" in names and "Квиз и игры" in names
    assert "Караоке" in rep.free          # никто не упоминал
    assert "Джаз и блюз" not in rep.free


def test_occupied_sorted_by_competitor_count():
    """Формат у двоих важнее формата у одного."""
    a = _snap("A", ["джаз"] * 3 + ["караоке"] * 5)
    b = _snap("B", ["джаз"] * 3)
    rep = gaps.analyze([a, b])
    assert rep.occupied[0]["name"] == "Джаз и блюз"      # 2 конкурента
    assert len(rep.occupied[0]["competitors"]) == 2


def test_thin_corpus_gives_no_free_verdict():
    """На трёх постах вывод «формат свободен» — шум, а не вывод."""
    rep = gaps.analyze([_snap("A", ["джаз", "джаз", "джаз"])])
    assert rep.posts_analyzed == 3
    assert rep.confidence == "низкая"
    assert rep.free == []
    assert "слишком мало" in rep.notice


def test_empty_corpus_is_honest():
    rep = gaps.analyze([_snap("A", [], ok=False), _snap("B", [])])
    assert rep.posts_analyzed == 0
    assert rep.confidence == "нет данных"
    assert rep.free == []
    assert "VK_SERVICE_TOKEN" in rep.notice
    assert set(rep.competitors_without_data) == {"A", "B"}


def test_notice_warns_absence_is_not_proof():
    """«Не встречается» ≠ «не проводят» — предупреждение обязано быть."""
    rep = gaps.analyze([_snap("A", ["джаз"] * 12)])
    assert "мог проводить его и не написать" in rep.notice


def test_confidence_levels():
    assert gaps._confidence(0) == "нет данных"
    assert gaps._confidence(5) == "низкая"
    assert gaps._confidence(20) == "средняя"
    assert gaps._confidence(50) == "хорошая"


def test_falls_back_to_latest_post_when_no_corpus():
    """Старые снимки без recent_post_texts не должны терять единственный пост."""
    s = CompetitorSnapshot(competitor_name="A", collected_at="x")
    vk = SourceSnapshot(source="vk", ok=True)
    vk.latest_post_text = "Джазовый вечер в пятницу"
    s.sources["vk"] = vk
    rep = gaps.analyze([s])
    assert rep.posts_analyzed == 1
    assert any(o["name"] == "Джаз и блюз" for o in rep.occupied)


def test_source_not_ok_is_ignored():
    rep = gaps.analyze([_snap("A", ["джаз"] * 12, ok=False)])
    assert rep.posts_analyzed == 0 and rep.competitors_without_data == ["A"]


# ── Обратная совместимость снимков ────────────────────────────────────
def test_old_snapshot_without_new_field_loads():
    """В хранилище лежат снимки без recent_post_texts — не падать на них."""
    d = {"source": "vk", "ok": True, "subscribers": 100, "latest_post_text": "джаз"}
    s = SourceSnapshot.from_dict(d)
    assert s.recent_post_texts == []
    assert s.latest_post_text == "джаз"


def test_snapshot_roundtrip_keeps_texts():
    vk = SourceSnapshot(source="vk", ok=True)
    vk.recent_post_texts = ["пост один", "пост два"]
    restored = SourceSnapshot.from_dict(vk.to_dict())
    assert restored.recent_post_texts == ["пост один", "пост два"]
