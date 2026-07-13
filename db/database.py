"""Единый доступ к PostgreSQL для настроек и контента.

Если DATABASE_URL не задан — модуль неактивен (db_enabled() == False), и
хранилища работают на локальных JSON-файлах (режим разработки). В проде
(Docker/сервер) DATABASE_URL задан → данные в PostgreSQL.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from config.settings import settings

log = logging.getLogger("restopulse.db")

_SCHEMA_READY = False
_LOCK = threading.Lock()


def db_enabled() -> bool:
    return bool(settings.database_url)


def _connect():
    import psycopg  # ленивый импорт — psycopg не нужен в JSON-режиме
    return psycopg.connect(settings.database_url)


def ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _LOCK:
        if _SCHEMA_READY:
            return
        sql = (Path(__file__).resolve().parent / "init.sql").read_text(encoding="utf-8")
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()
        _SCHEMA_READY = True


# ── Ключ-значение (настройки: провайдеры, каналы) ─────────────────────
def kv_get(key: str) -> dict | None:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
        row = cur.fetchone()
    if not row:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def kv_set(key: str, value: dict) -> None:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        conn.commit()


# ── Посты (контент) ───────────────────────────────────────────────────
def posts_all() -> list[dict]:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT data FROM content_posts ORDER BY created_at DESC")
        return [(r[0] if isinstance(r[0], dict) else json.loads(r[0])) for r in cur.fetchall()]


def posts_get(post_id: str) -> dict | None:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT data FROM content_posts WHERE id = %s", (post_id,))
        row = cur.fetchone()
    if not row:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def posts_upsert(post: dict) -> None:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO content_posts (id, data, created_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            (post["id"], json.dumps(post, ensure_ascii=False), post.get("created_at", "")),
        )
        conn.commit()


def posts_delete(post_id: str) -> bool:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM content_posts WHERE id = %s", (post_id,))
        deleted = cur.rowcount
        conn.commit()
    return bool(deleted)


# ── Гости (CRM) ───────────────────────────────────────────────────────
def guests_all() -> list[dict]:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT data FROM crm_guests ORDER BY created_at DESC")
        return [(r[0] if isinstance(r[0], dict) else json.loads(r[0])) for r in cur.fetchall()]


def guests_get(guest_id: str) -> dict | None:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT data FROM crm_guests WHERE id = %s", (guest_id,))
        row = cur.fetchone()
    if not row:
        return None
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def guests_upsert_many(guests: list[dict]) -> None:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        for g in guests:
            cur.execute(
                "INSERT INTO crm_guests (id, data, created_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (g["id"], json.dumps(g, ensure_ascii=False), g.get("created_at", "")),
            )
        conn.commit()


def guests_clear() -> None:
    ensure_schema()
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM crm_guests")
        conn.commit()


def healthcheck() -> bool:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception as exc:
        log.warning("Проверка БД не прошла: %s", exc)
        return False
