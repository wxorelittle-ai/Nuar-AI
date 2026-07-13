"""Хранилище постов (черновики/очередь/опубликованные) в data/content.json."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from config.settings import DATA_DIR
from .models import Post

_LOCK = threading.Lock()


class ContentStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "content.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)

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

    def list(self) -> list[Post]:
        from db import database
        if database.db_enabled():
            return [Post.from_dict(r) for r in database.posts_all()]
        posts = [Post.from_dict(r) for r in self._load()]
        return sorted(posts, key=lambda p: p.created_at, reverse=True)

    def get(self, post_id: str) -> Post | None:
        from db import database
        if database.db_enabled():
            row = database.posts_get(post_id)
            return Post.from_dict(row) if row else None
        for r in self._load():
            if r.get("id") == post_id:
                return Post.from_dict(r)
        return None

    def upsert(self, post: Post) -> Post:
        from db import database
        if database.db_enabled():
            database.posts_upsert(post.to_dict())
            return post
        with _LOCK:
            rows = self._load()
            for i, r in enumerate(rows):
                if r.get("id") == post.id:
                    rows[i] = post.to_dict()
                    break
            else:
                rows.append(post.to_dict())
            self._save(rows)
        return post

    def delete(self, post_id: str) -> bool:
        from db import database
        if database.db_enabled():
            return database.posts_delete(post_id)
        with _LOCK:
            rows = self._load()
            new = [r for r in rows if r.get("id") != post_id]
            if len(new) == len(rows):
                return False
            self._save(new)
        return True


store = ContentStore()
