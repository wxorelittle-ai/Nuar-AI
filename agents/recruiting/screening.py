"""Оценка кандидата под вакансию: соответствие, признаки ИИ-текста, дубликаты.

Три честных блока:
  1. fit — соответствие вакансии. Детерминированно: покрытие обязательных
     навыков доминирует, желательные дают бонус, опыт сверяется с минимумом.
  2. ai_signals — ПРИЗНАКИ машинного текста, не приговор. Настоящий детектор
     ИИ ненадёжен и даёт ложные срабатывания; поэтому мы отдаём сигналы с
     оценкой и явной оговоркой, а решение оставляем человеку.
  3. duplicates — совпадения ВНУТРИ пула откликов (кто у кого списал, или
     скопировал текст вакансии). Это можно проверить строго, без интернета.

Всё здесь — чистые функции без сети: тестируются и объяснимы.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# ── Нормализация текста ───────────────────────────────────────────────
_WORD = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


def norm(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


def words(text: str) -> list[str]:
    return _WORD.findall(norm(text))


def sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


# ── 1. Соответствие вакансии ──────────────────────────────────────────
def _has_skill(text_norm: str, skill: str) -> bool:
    """Навык присутствует, если его нормализованная форма — подстрока текста."""
    s = norm(skill).strip()
    return bool(s) and s in text_norm


def experience_years(text: str) -> float | None:
    """Грубая оценка стажа из фраз «опыт 5 лет», «3 года», «стаж — 2»."""
    t = norm(text)
    best = None
    for m in re.finditer(r"(\d{1,2})\s*(?:\+)?\s*(год|года|лет)", t):
        val = int(m.group(1))
        if 0 < val <= 50:
            best = max(best or 0, val)
    return float(best) if best is not None else None


@dataclass
class FitResult:
    score: int = 0                       # 0..100
    matched_must: list[str] = field(default_factory=list)
    missing_must: list[str] = field(default_factory=list)
    matched_nice: list[str] = field(default_factory=list)
    experience_years: float | None = None
    experience_ok: bool | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def score_fit(resume_text: str, *, must_have: list[str] | None = None,
              nice_to_have: list[str] | None = None,
              min_experience: float = 0.0) -> FitResult:
    must = [s for s in (must_have or []) if s.strip()]
    nice = [s for s in (nice_to_have or []) if s.strip()]
    tn = norm(resume_text)

    matched_must = [s for s in must if _has_skill(tn, s)]
    missing_must = [s for s in must if s not in matched_must]
    matched_nice = [s for s in nice if _has_skill(tn, s)]

    exp = experience_years(resume_text)
    exp_ok = None
    if min_experience > 0:
        exp_ok = exp is not None and exp >= min_experience

    # Веса: обязательные навыки — 70, желательные — 20, опыт — 10.
    must_part = (len(matched_must) / len(must) * 70) if must else 70
    nice_part = (len(matched_nice) / len(nice) * 20) if nice else 20
    if min_experience > 0:
        exp_part = 10 if exp_ok else 0
    else:
        exp_part = 10
    score = round(must_part + nice_part + exp_part)

    bits = []
    if must:
        bits.append(f"обязательные: {len(matched_must)}/{len(must)}")
    if nice:
        bits.append(f"желательные: {len(matched_nice)}/{len(nice)}")
    if min_experience > 0:
        bits.append(f"опыт {exp if exp is not None else '?'} лет из {min_experience:g}")
    return FitResult(score=min(score, 100), matched_must=matched_must,
                     missing_must=missing_must, matched_nice=matched_nice,
                     experience_years=exp, experience_ok=exp_ok,
                     reason="; ".join(bits))


# ── 2. Признаки машинного текста (сигналы, НЕ приговор) ────────────────
# Клише, которыми ИИ и «скачанные из интернета» резюме забиты без конкретики.
BUZZWORDS = [
    "коммуникабельн", "стрессоустойчив", "ответственн", "командный игрок",
    "нацелен на результат", "быстро обучаем", "многозадачн", "клиентоориентир",
    "пунктуальн", "исполнительн", "активная жизненная позиция", "легко нахожу общий язык",
]
# Обороты, характерные для генеративного текста
LLM_MARKERS = [
    "важно отметить", "стоит отметить", "в заключение", "таким образом",
    "динамичн", "в современном мире", "играет важную роль", "не только", "но и",
]


@dataclass
class AISignals:
    score: int = 0                       # 0..100 — «подозрительность», не вероятность
    level: str = "низкая"                # низкая | средняя | высокая
    flags: list[str] = field(default_factory=list)
    disclaimer: str = ("Это признаки, а не приговор. Надёжного детектора ИИ не "
                       "существует; проверяйте на собеседовании, не отказывайте только по этому.")

    def to_dict(self) -> dict:
        return asdict(self)


def _burstiness(sents: list[str]) -> float:
    """Разброс длин предложений. У живого текста он выше, у машинного — ровнее."""
    lens = [len(words(s)) for s in sents if s]
    if len(lens) < 3:
        return 1.0
    mean = sum(lens) / len(lens)
    if mean == 0:
        return 1.0
    var = sum((x - mean) ** 2 for x in lens) / len(lens)
    return (var ** 0.5) / mean          # коэффициент вариации


def ai_signals(text: str) -> AISignals:
    tn = norm(text)
    toks = words(text)
    sents = sentences(text)
    flags: list[str] = []
    score = 0

    buzz = [b for b in BUZZWORDS if b in tn]
    if len(buzz) >= 3:
        score += 30
        flags.append(f"много общих клише без конкретики ({len(buzz)})")
    elif len(buzz) == 2:
        score += 15
        flags.append("шаблонные формулировки")

    markers = [m for m in LLM_MARKERS if m in tn]
    if len(markers) >= 2:
        score += 25
        flags.append(f"обороты генеративного текста ({len(markers)})")

    # Конкретика: цифры, годы, названия. Их отсутствие — тревожный сигнал.
    digits = sum(1 for t in toks if any(c.isdigit() for c in t))
    if toks and digits == 0 and len(toks) > 40:
        score += 20
        flags.append("нет ни одной цифры/конкретики (мест, дат, цифр)")

    if len(sents) >= 4:
        b = _burstiness(sents)
        if b < 0.35:
            score += 25
            flags.append("неестественно ровные предложения по длине")

    score = min(score, 100)
    level = "высокая" if score >= 60 else "средняя" if score >= 30 else "низкая"
    return AISignals(score=score, level=level, flags=flags)


# ── 3. Дубликаты внутри пула ──────────────────────────────────────────
def shingles(text: str, k: int = 4) -> set:
    """Множество словных k-грамм — основа для сравнения на списывание."""
    w = words(text)
    if len(w) < k:
        return {" ".join(w)} if w else set()
    return {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def similarity(text_a: str, text_b: str, k: int = 4) -> float:
    return round(jaccard(shingles(text_a, k), shingles(text_b, k)), 3)


DUP_THRESHOLD = 0.35     # выше — тексты подозрительно похожи


@dataclass
class DuplicateHit:
    other_id: str = ""
    other_name: str = ""
    ratio: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def find_duplicates(items: list[dict], *, threshold: float = DUP_THRESHOLD) -> dict[str, DuplicateHit]:
    """items — [{id, name, text}]. Возвращает {id: самое похожее совпадение}."""
    prepared = [(it, shingles(it.get("text", ""))) for it in items]
    out: dict[str, DuplicateHit] = {}
    for i, (a, sa) in enumerate(prepared):
        best: DuplicateHit | None = None
        for j, (b, sb) in enumerate(prepared):
            if i == j:
                continue
            r = round(jaccard(sa, sb), 3)
            if r >= threshold and (best is None or r > best.ratio):
                best = DuplicateHit(other_id=b.get("id", ""), other_name=b.get("name", ""), ratio=r)
        if best:
            out[a.get("id", "")] = best
    return out
