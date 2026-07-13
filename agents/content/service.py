"""Сервис контент-агента: генерация, черновики, публикация, автопубликация."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from agents.llm.base import LLMError
from agents.publishers.base import PublishResult
from agents.publishers.registry import get_publisher, CHANNELS, CHANNEL_BY_KEY
from agents.moderation import service as moderation
from config.store import store as settings_store, CHANNEL_SECRET_FIELDS, mask_secret
from .models import Post, NETWORKS, CONTENT_LINES, STATUSES, DRAFT, APPROVED, PUBLISHED, FAILED

# Сколько раз повторять неудачную автопубликацию, прежде чем пометить «Ошибка»
MAX_PUBLISH_ATTEMPTS = 3
from .store import store as content_store
from . import generator
from . import ideas as ideas_mod

log = logging.getLogger("restopulse.content")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Генерация ─────────────────────────────────────────────────────────
def generate(network: str, content_line: str, topic: str = "",
             restaurant: str = "Nuar", tone: str = "") -> str:
    if network not in NETWORKS:
        network = "vk"
    return generator.generate_post(network=network, content_line=content_line,
                                   topic=topic, restaurant=restaurant, tone=tone)


# ── Черновики ─────────────────────────────────────────────────────────
def save_post(data: dict) -> Post:
    """Создаёт или обновляет пост. Ожидает dict от UI."""
    pid = data.get("id") or uuid.uuid4().hex[:12]
    existing = content_store.get(pid)
    post = existing or Post(id=pid, created_at=_now())
    post.network = data.get("network", post.network or "vk")
    post.content_line = data.get("content_line", post.content_line)
    post.topic = data.get("topic", post.topic)
    post.text = data.get("text", post.text)
    post.scheduled_at = data.get("scheduled_at", post.scheduled_at)
    if data.get("status") in STATUSES:
        post.status = data["status"]
    return content_store.upsert(post)


def list_posts() -> list[dict]:
    return [p.to_dict() for p in content_store.list()]


def ideas(network: str = "vk") -> list[dict]:
    """Идеи для постов из разведки + базовые (для панели «Идеи»)."""
    if network not in NETWORKS:
        network = "vk"
    return ideas_mod.latest_ideas(network)


def delete_post(post_id: str) -> bool:
    return content_store.delete(post_id)


# ── Публикация ────────────────────────────────────────────────────────
def moderate(text: str, network: str = "vk") -> dict:
    """Проверка поста модерацией (для UI-кнопки «Проверить»)."""
    return moderation.moderate(text, network).to_dict()


def publish_post(post_id: str, *, enforce_moderation: bool = True) -> Post:
    post = content_store.get(post_id)
    if post is None:
        raise ValueError("Пост не найден")
    if not post.text.strip():
        raise ValueError("Пустой текст поста")
    pub = get_publisher(post.network)
    if pub is None:
        raise ValueError(f"Нет публикатора для сети {post.network}")

    # Шлюз модерации: жёсткие нарушения не пропускаем к публикации
    if enforce_moderation:
        mod = moderation.moderate(post.text, post.network)
        if not mod.ok:
            post.error = "Модерация: " + "; ".join(
                i.message for i in mod.issues if i.level == moderation.BLOCK)
            content_store.upsert(post)
            raise moderation.ModerationError(mod)

    result: PublishResult = pub.publish(post.text)
    if result.ok:
        post.status = PUBLISHED
        post.published_at = _now()
        post.link = result.link
        post.error = ""
    else:
        post.error = result.error
    return content_store.upsert(post)


def auto_publish_due(now: datetime | None = None) -> list[Post]:
    """Публикует утверждённые посты, у которых наступило время (scheduled_at).
    Вызывается планировщиком. Черновики и неутверждённые не трогаем."""
    now = now or datetime.now(timezone.utc)
    published: list[Post] = []
    for post in content_store.list():
        if post.status != APPROVED or not post.scheduled_at:
            continue
        try:
            due = datetime.fromisoformat(post.scheduled_at)
        except ValueError:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due > now:
            continue

        log.info("Автопубликация поста %s (%s)", post.id, post.network)
        try:
            result = publish_post(post.id)
        except moderation.ModerationError:
            fresh = content_store.get(post.id)
            fresh.status = FAILED
            fresh.error = "Модерация заблокировала автопубликацию"
            content_store.upsert(fresh)
            continue

        if result.status == PUBLISHED:
            published.append(result)
            continue

        # Ошибка публикации — повторим позже, после лимита попыток пометим «Ошибка»
        fresh = content_store.get(post.id)
        fresh.attempts = (fresh.attempts or 0) + 1
        if fresh.attempts >= MAX_PUBLISH_ATTEMPTS:
            fresh.status = FAILED
            log.warning("Пост %s помечен «Ошибка» после %s попыток", post.id, fresh.attempts)
        content_store.upsert(fresh)
    return published


# ── Настройки каналов для UI ──────────────────────────────────────────
def ui_channels() -> dict:
    out = []
    for meta in CHANNELS:
        ckey = meta["key"]
        stored = settings_store.get_channel_config(ckey)
        secret = CHANNEL_SECRET_FIELDS.get(ckey, set())
        values = {}
        for f in meta["fields"]:
            name = f["name"]
            values[name] = mask_secret(stored.get(name, "")) if name in secret else stored.get(name, f.get("default", ""))
        out.append({**meta, "values": values})
    return {"channels": out}


def apply_channels(channels_patch: dict) -> None:
    settings_store.update_channels(channels_patch)


def meta() -> dict:
    """Справочники для UI композера."""
    return {
        "networks": [{"value": k, "label": v} for k, v in NETWORKS.items()],
        "content_lines": CONTENT_LINES,
        "statuses": STATUSES,
    }
