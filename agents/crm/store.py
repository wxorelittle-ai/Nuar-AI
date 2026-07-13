"""Хранилище гостевой базы (JSON локально / PostgreSQL в проде)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from config.settings import DATA_DIR
from .models import Guest

_LOCK = threading.Lock()


class GuestStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "guests.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # JSON-режим
    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _save(self, rows: list[dict]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ── API ───────────────────────────────────────────────────────────
    def list(self) -> list[Guest]:
        from db import database
        rows = database.guests_all() if database.db_enabled() else self._load()
        return [Guest.from_dict(r) for r in rows]

    def get(self, guest_id: str) -> Guest | None:
        from db import database
        if database.db_enabled():
            row = database.guests_get(guest_id)
            return Guest.from_dict(row) if row else None
        for r in self._load():
            if r.get("id") == guest_id:
                return Guest.from_dict(r)
        return None

    def replace_all(self, guests: list[Guest]) -> None:
        """Полностью заменяет базу (импорт CSV перезаписывает предыдущую)."""
        from db import database
        rows = [g.to_dict() for g in guests]
        if database.db_enabled():
            database.guests_clear()
            database.guests_upsert_many(rows)
            return
        with _LOCK:
            self._save(rows)


store = GuestStore()
