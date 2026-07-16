"""Окна возможностей: какие форматы конкуренты НЕ упоминают.

Идея: собрать корпус текстов конкурентов (посты VK) и разметить по словарю
форматов. Формат, который не встречается ни у кого, — кандидат в окно: можно
зайти первым в округе.

ЧЕСТНОСТЬ ФОРМУЛИРОВОК — главное здесь. Отсутствие формата в постах НЕ равно
«конкурент его не проводит»: он мог не написать об этом. Поэтому:
  • говорим «не встречается в их постах», а не «они этого не делают»;
  • всегда отдаём confidence по объёму корпуса — на трёх постах выводы не строят;
  • при пустом корпусе честно возвращаем «нет данных», а не «всё свободно».
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict, field

log = logging.getLogger("restopulse.gaps")

# Словарь форматов: название → ключевые подстроки (нижний регистр, без окончаний).
# Подбирались так, чтобы не ловить лишнего: короткие/многозначные слова опасны.
FORMATS: dict[str, list[str]] = {
    "Живая музыка": ["живая музык", "живой звук", "концерт", "выступлен", "бэнд", "музыкант"],
    "Джаз и блюз": ["джаз", "jazz", "блюз", "саксофон"],
    "Диджей и танцы": ["диджей", "dj-сет", "танцпол", "вечеринк"],
    "Караоке": ["караоке"],
    "Квиз и игры": ["квиз", "quiz", "викторин", "мафия", "настольн"],
    "Стендап": ["стендап", "стенд-ап", "stand-up", "открытый микрофон", "комик"],
    "Дегустация": ["дегустац", "тейстинг", "гастроужин", "гастро-ужин", "сет-меню"],
    "Мастер-класс": ["мастер-класс", "мастеркласс", "воркшоп"],
    "Кинопоказ": ["кинопоказ", "кинов", "показ фильма", "киновечер"],
    "Бранч и завтраки": ["бранч", "завтрак"],
    "Винный вечер": ["винный вечер", "сомелье", "винотек", "дегустация вин"],
    "Коктейльный вечер": ["коктейльн", "миксолог", "гость-бармен", "барное шоу"],
    "Лекция и книжный клуб": ["лекци", "книжный клуб", "читк", "поэтическ"],
    "Банкеты и корпоративы": ["банкет", "корпоратив", "закрытое мероприят"],
    "Поэзия и арт": ["выставк", "арт-", "художник", "фотовыставк"],
}

MIN_POSTS_FOR_VERDICT = 10   # ниже этого «свободно» — не вывод, а шум


@dataclass
class FormatUsage:
    name: str
    competitors: list[str] = field(default_factory=list)
    mentions: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GapReport:
    posts_analyzed: int = 0
    competitors_with_data: list[str] = field(default_factory=list)
    competitors_without_data: list[str] = field(default_factory=list)
    occupied: list[dict] = field(default_factory=list)   # форматы, что встречаются
    free: list[str] = field(default_factory=list)        # не встречаются ни у кого
    confidence: str = "нет данных"                       # нет данных | низкая | средняя | хорошая
    notice: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def detect_formats(text: str) -> set[str]:
    """Какие форматы упоминаются в тексте."""
    t = (text or "").lower().replace("ё", "е")
    found = set()
    for name, keys in FORMATS.items():
        for k in keys:
            if k.replace("ё", "е") in t:
                found.add(name)
                break
    return found


def _confidence(posts: int) -> str:
    if posts == 0:
        return "нет данных"
    if posts < MIN_POSTS_FOR_VERDICT:
        return "низкая"
    if posts < 40:
        return "средняя"
    return "хорошая"


def _corpus(snapshot) -> list[str]:
    """Тексты конкурента из снимка (VK-посты + последний пост)."""
    vk = (snapshot.sources or {}).get("vk")
    if not vk or not vk.ok:
        return []
    texts = list(getattr(vk, "recent_post_texts", None) or [])
    if not texts and vk.latest_post_text:
        texts = [vk.latest_post_text]
    return [t for t in texts if t and t.strip()]


def analyze(snapshots: list) -> GapReport:
    """Строит отчёт по окнам возможностей из снимков конкурентов."""
    rep = GapReport()
    usage: dict[str, FormatUsage] = {}

    for snap in snapshots:
        name = getattr(snap, "competitor_name", "") or "конкурент"
        texts = _corpus(snap)
        if not texts:
            rep.competitors_without_data.append(name)
            continue
        rep.competitors_with_data.append(name)
        rep.posts_analyzed += len(texts)
        for text in texts:
            for fmt in detect_formats(text):
                u = usage.setdefault(fmt, FormatUsage(name=fmt))
                u.mentions += 1
                if name not in u.competitors:
                    u.competitors.append(name)

    rep.occupied = [u.to_dict() for u in
                    sorted(usage.values(), key=lambda u: (-len(u.competitors), -u.mentions))]
    rep.confidence = _confidence(rep.posts_analyzed)

    # «Свободно» имеет смысл только при достаточном корпусе
    if rep.posts_analyzed >= MIN_POSTS_FOR_VERDICT:
        rep.free = [f for f in FORMATS if f not in usage]
    rep.notice = _notice(rep)
    return rep


def _notice(rep: GapReport) -> str:
    if rep.posts_analyzed == 0:
        return ("Нет текстов конкурентов для анализа. Нужен VK_SERVICE_TOKEN в .env "
                "(бесплатный сервисный ключ приложения VK на dev.vk.com) и заполненные "
                "vk_domain у конкурентов в config/competitors.yaml, затем — прогон разведки.")
    base = (f"Разобрано постов: {rep.posts_analyzed} "
            f"(конкурентов с данными: {len(rep.competitors_with_data)}). "
            f"Достоверность: {rep.confidence}.")
    if rep.posts_analyzed < MIN_POSTS_FOR_VERDICT:
        base += " Постов слишком мало — выводы о свободных форматах не делаем."
    else:
        base += (" Важно: «не встречается» означает лишь, что формат не упомянут в постах — "
                 "конкурент мог проводить его и не написать.")
    if rep.competitors_without_data:
        base += f" Без данных: {', '.join(rep.competitors_without_data)}."
    return base


def latest_report() -> GapReport:
    """Отчёт по последним снимкам из хранилища (best-effort)."""
    try:
        from config.settings import load_competitors_config
        from db.repository import get_repository
        cfg = load_competitors_config()
        repo = get_repository()
        snaps = []
        for c in cfg.get("competitors", []):
            name = c.get("name")
            if not name:
                continue
            snap = repo.latest(name)
            if snap is not None:
                snaps.append(snap)
        return analyze(snaps)
    except Exception as exc:
        log.debug("Снимки конкурентов недоступны: %s", exc)
        rep = GapReport()
        rep.notice = _notice(rep)
        return rep
