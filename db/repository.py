"""Хранилище снимков конкурентов.

Две реализации за единым интерфейсом:
  • PostgresRepository — прод (DATABASE_URL задан);
  • JsonRepository     — локальный файл data/snapshots.json (по умолчанию).

get_repository() выбирает нужную по настройкам. Оба хранят и отдают
CompetitorSnapshot, а также умеют доставать «предыдущий снимок» для diff.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from config.settings import settings, DATA_DIR
from models.competitor import CompetitorSnapshot

log = logging.getLogger("restopulse.repository")


class Repository(Protocol):
    def save_snapshot(self, snap: CompetitorSnapshot) -> None: ...
    def latest_before(self, competitor_name: str, before_iso: str) -> CompetitorSnapshot | None: ...
    def latest(self, competitor_name: str) -> CompetitorSnapshot | None: ...
    def save_digest(self, week_label: str, body: str, sent_ok: bool) -> None: ...


# ── JSON-хранилище (fallback без БД) ─────────────────────────────────
class JsonRepository:
    """Простое файловое хранилище: список снимков в data/snapshots.json.

    Достаточно, чтобы уже видеть недельные изменения без поднятия PostgreSQL."""

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "snapshots.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("Повреждён %s — начинаю с пустой истории", self.path)
            return []

    def _dump(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_snapshot(self, snap: CompetitorSnapshot) -> None:
        rows = self._load()
        rows.append({"kind": "snapshot", **snap.to_dict()})
        self._dump(rows)

    def latest_before(self, competitor_name: str, before_iso: str) -> CompetitorSnapshot | None:
        candidates = [
            r for r in self._load()
            if r.get("kind") == "snapshot"
            and r.get("competitor_name") == competitor_name
            and r.get("collected_at", "") < before_iso
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda r: r.get("collected_at", ""))
        return CompetitorSnapshot.from_dict(latest)

    def latest(self, competitor_name: str) -> CompetitorSnapshot | None:
        candidates = [
            r for r in self._load()
            if r.get("kind") == "snapshot" and r.get("competitor_name") == competitor_name
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda r: r.get("collected_at", ""))
        return CompetitorSnapshot.from_dict(latest)

    def save_digest(self, week_label: str, body: str, sent_ok: bool) -> None:
        rows = self._load()
        rows.append({"kind": "digest", "week_label": week_label, "body": body, "sent_ok": sent_ok})
        self._dump(rows)


# ── PostgreSQL-хранилище (прод) ──────────────────────────────────────
class PostgresRepository:
    """Хранилище на PostgreSQL. Требует psycopg и заданного DATABASE_URL.
    Схема создаётся из db/init.sql (см. docker-compose / ensure_schema)."""

    def __init__(self, dsn: str):
        import psycopg  # импорт внутри, чтобы psycopg не требовался для JSON-режима

        self._psycopg = psycopg
        self.dsn = dsn
        self.ensure_schema()

    def _connect(self):
        return self._psycopg.connect(self.dsn)

    def ensure_schema(self) -> None:
        sql = (Path(__file__).resolve().parent / "init.sql").read_text(encoding="utf-8")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()

    def save_snapshot(self, snap: CompetitorSnapshot) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO competitor_snapshots (competitor_name, collected_at, payload) "
                "VALUES (%s, %s, %s)",
                (snap.competitor_name, snap.collected_at, json.dumps(snap.to_dict(), ensure_ascii=False)),
            )
            conn.commit()

    def latest_before(self, competitor_name: str, before_iso: str) -> CompetitorSnapshot | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM competitor_snapshots "
                "WHERE competitor_name = %s AND collected_at < %s "
                "ORDER BY collected_at DESC LIMIT 1",
                (competitor_name, before_iso),
            )
            row = cur.fetchone()
        if not row:
            return None
        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return CompetitorSnapshot.from_dict(payload)

    def latest(self, competitor_name: str) -> CompetitorSnapshot | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM competitor_snapshots "
                "WHERE competitor_name = %s ORDER BY collected_at DESC LIMIT 1",
                (competitor_name,),
            )
            row = cur.fetchone()
        if not row:
            return None
        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return CompetitorSnapshot.from_dict(payload)

    def save_digest(self, week_label: str, body: str, sent_ok: bool) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO digests (week_label, body, sent_ok) VALUES (%s, %s, %s)",
                (week_label, body, sent_ok),
            )
            conn.commit()


def get_repository() -> Repository:
    """Фабрика: PostgreSQL при заданном DATABASE_URL, иначе JSON-файл."""
    if settings.use_postgres:
        try:
            log.info("Хранилище: PostgreSQL")
            return PostgresRepository(settings.database_url)
        except Exception as exc:  # не роняем прогон из-за БД — падаем в JSON
            log.error("PostgreSQL недоступен (%s) — переключаюсь на JSON-файл", exc)
    log.info("Хранилище: локальный JSON-файл")
    return JsonRepository()
