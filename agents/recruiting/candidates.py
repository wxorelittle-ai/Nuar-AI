"""Витрина вакансий и кандидатов: хранение, оценка, рейтинг.

Модель простая: вакансия задаёт требования (обязательные/желательные навыки,
минимальный опыт), кандидат — это резюме (вставленный текст или отклик).
Каждый кандидат оценивается конвейером screening.py: соответствие + признаки
ИИ-текста. Дубликаты (списывание) считаются по всему пулу вакансии при рейтинге.

Хранение — как в config/store.py: JSON-файл локально, kv в Postgres.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from config.settings import DATA_DIR
from . import screening

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Vacancy:
    id: str
    title: str = ""
    must_have: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    min_experience: float = 0.0
    city: str = ""
    notes: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Vacancy":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Candidate:
    id: str
    vacancy_id: str = ""
    name: str = ""
    source: str = "paste"           # paste | hh | rabota | otklik
    text: str = ""
    contact: str = ""
    created_at: str = ""
    # результат оценки (заполняется при сохранении/пересчёте)
    fit: dict = field(default_factory=dict)
    ai: dict = field(default_factory=dict)
    duplicate: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


class ScreeningStore:
    def __init__(self, path=None):
        self.path = path or (DATA_DIR / "recruiting.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _defaults(data: dict) -> dict:
        data = data or {}
        data.setdefault("vacancies", {})
        data.setdefault("candidates", {})
        return data

    def _load(self) -> dict:
        from db import database
        if database.db_enabled():
            return self._defaults(database.kv_get("recruiting"))
        if not self.path.exists():
            return self._defaults({})
        try:
            return self._defaults(json.loads(self.path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return self._defaults({})

    def _save(self, data: dict) -> None:
        from db import database
        if database.db_enabled():
            database.kv_set("recruiting", data)
            return
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ── вакансии ──────────────────────────────────────────────────────
    def list_vacancies(self) -> list[Vacancy]:
        return [Vacancy.from_dict(v) for v in self._load()["vacancies"].values()]

    def get_vacancy(self, vid: str) -> Vacancy | None:
        v = self._load()["vacancies"].get(vid)
        return Vacancy.from_dict(v) if v else None

    def upsert_vacancy(self, vac: Vacancy) -> Vacancy:
        with _LOCK:
            data = self._load()
            data["vacancies"][vac.id] = vac.to_dict()
            self._save(data)
        return vac

    def delete_vacancy(self, vid: str) -> bool:
        with _LOCK:
            data = self._load()
            existed = data["vacancies"].pop(vid, None) is not None
            # каскад: убрать кандидатов этой вакансии
            data["candidates"] = {k: v for k, v in data["candidates"].items()
                                  if v.get("vacancy_id") != vid}
            self._save(data)
        return existed

    # ── кандидаты ─────────────────────────────────────────────────────
    def candidates_for(self, vid: str) -> list[Candidate]:
        return [Candidate.from_dict(c) for c in self._load()["candidates"].values()
                if c.get("vacancy_id") == vid]

    def upsert_candidate(self, cand: Candidate) -> Candidate:
        with _LOCK:
            data = self._load()
            data["candidates"][cand.id] = cand.to_dict()
            self._save(data)
        return cand

    def delete_candidate(self, cid: str) -> bool:
        with _LOCK:
            data = self._load()
            existed = data["candidates"].pop(cid, None) is not None
            self._save(data)
        return existed


store = ScreeningStore()


# ── Сервис ────────────────────────────────────────────────────────────
def create_vacancy(data: dict) -> Vacancy:
    vac = Vacancy(
        id=data.get("id") or _uid(),
        title=(data.get("title") or "").strip(),
        must_have=_clean_list(data.get("must_have")),
        nice_to_have=_clean_list(data.get("nice_to_have")),
        min_experience=_to_float(data.get("min_experience")),
        city=(data.get("city") or "").strip(),
        notes=(data.get("notes") or "").strip(),
        created_at=data.get("created_at") or _now(),
    )
    return store.upsert_vacancy(vac)


def add_candidate(vacancy_id: str, *, name: str, text: str,
                  source: str = "paste", contact: str = "") -> Candidate:
    vac = store.get_vacancy(vacancy_id)
    if vac is None:
        raise ValueError("Вакансия не найдена")
    text = (text or "").strip()
    if not text:
        raise ValueError("Пустой текст резюме")
    cand = Candidate(
        id=_uid(), vacancy_id=vacancy_id,
        name=(name or "").strip() or "Без имени",
        source=source, text=text, contact=(contact or "").strip(),
        created_at=_now(),
    )
    _evaluate(cand, vac)
    return store.upsert_candidate(cand)


def _evaluate(cand: Candidate, vac: Vacancy) -> None:
    fit = screening.score_fit(cand.text, must_have=vac.must_have,
                              nice_to_have=vac.nice_to_have,
                              min_experience=vac.min_experience)
    cand.fit = fit.to_dict()
    cand.ai = screening.ai_signals(cand.text).to_dict()


def ranking(vacancy_id: str) -> dict:
    """Кандидаты вакансии с рейтингом и пересчётом дубликатов по всему пулу."""
    vac = store.get_vacancy(vacancy_id)
    if vac is None:
        raise ValueError("Вакансия не найдена")
    cands = store.candidates_for(vacancy_id)

    # Дубликаты — сравнение по всему пулу (кто у кого списал)
    dups = screening.find_duplicates(
        [{"id": c.id, "name": c.name, "text": c.text} for c in cands])

    rows = []
    for c in cands:
        d = c.to_dict()
        hit = dups.get(c.id)
        d["duplicate"] = hit.to_dict() if hit else {}
        rows.append(d)

    # Сортировка: сперва по соответствию, затем меньшая ИИ-подозрительность
    rows.sort(key=lambda r: (r["fit"].get("score", 0),
                             -r["ai"].get("score", 0)), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"vacancy": vac.to_dict(), "candidates": rows,
            "count": len(rows), "duplicates_found": len(dups)}


def reevaluate_vacancy(vacancy_id: str) -> int:
    """Пересчитать оценку всех кандидатов (после правки требований вакансии)."""
    vac = store.get_vacancy(vacancy_id)
    if vac is None:
        raise ValueError("Вакансия не найдена")
    n = 0
    for c in store.candidates_for(vacancy_id):
        _evaluate(c, vac)
        store.upsert_candidate(c)
        n += 1
    return n


def _clean_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return []


def _to_float(v) -> float:
    try:
        return max(0.0, float(v))
    except (TypeError, ValueError):
        return 0.0
