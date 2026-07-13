"""Сборка и отправка недельного разведдайджеста.

Пайплайн:
  build_digest()   — сравнивает свежие снимки с прошлыми (из репозитория),
                     превращает изменения в список DigestChange + рекомендацию;
  render_markdown() — рендерит Digest в Telegram Markdown;
  send_digest()    — рендерит, отправляет в Telegram, пишет в аудит.

Рекомендация формируется правилами (rule-based) — работает без LLM. Позже
сюда можно подключить Claude API для более «человеческой» формулировки.
"""
from __future__ import annotations

import logging

from models.competitor import Competitor, CompetitorSnapshot, SourceSnapshot
from models.digest import (
    Digest, DigestChange, IMPORTANT, RATING, VK_ACTIVITY, MEDIA,
)
from db.repository import Repository
from bot.telegram_bot import send_message

log = logging.getLogger("restopulse.digest")

# Порог, ниже которого изменение рейтинга считаем шумом
RATING_EPS = 0.05


def _priority_weight(competitor: Competitor) -> int:
    return {"high": 100, "medium": 50, "low": 10}.get(competitor.priority, 50)


def _best_rating(snap: CompetitorSnapshot) -> tuple[str, SourceSnapshot] | None:
    """Возвращает (источник, снимок) с валидным рейтингом — предпочитая 2ГИС."""
    for src_name in ("dgis", "yandex"):
        s = snap.sources.get(src_name)
        if s and s.ok and s.rating is not None:
            return src_name, s
    return None


def _compare_competitor(
    competitor: Competitor,
    current: CompetitorSnapshot,
    previous: CompetitorSnapshot | None,
) -> list[DigestChange]:
    """Строит список изменений по одному конкуренту."""
    changes: list[DigestChange] = []
    base_weight = _priority_weight(competitor)
    name = competitor.name

    # ── Рейтинг (2ГИС/Яндекс) ────────────────────────────────────────
    cur_rating = _best_rating(current)
    if cur_rating:
        src_name, cur_src = cur_rating
        prev_src = previous.sources.get(src_name) if previous else None
        if prev_src and prev_src.ok and prev_src.rating is not None:
            delta = round(cur_src.rating - prev_src.rating, 2)
            if abs(delta) >= RATING_EPS:
                sign = "+" if delta > 0 else ""
                extra = ""
                if cur_src.reviews_count and prev_src.reviews_count:
                    diff_reviews = cur_src.reviews_count - prev_src.reviews_count
                    if diff_reviews:
                        extra = f" ({'+' if diff_reviews > 0 else ''}{diff_reviews} отзывов)"
                changes.append(DigestChange(
                    name, RATING,
                    f"{name}: {prev_src.rating} → {cur_src.rating} ({sign}{delta}){extra}",
                    weight=base_weight + int(abs(delta) * 100),
                ))
        else:
            # Первый замер — фиксируем как базовую точку (без «изменения»)
            changes.append(DigestChange(
                name, RATING,
                f"{name}: {cur_src.rating} (первый замер, {cur_src.reviews_count or '—'} отзывов)",
                weight=base_weight,
            ))

    # ── Активность в VK ──────────────────────────────────────────────
    vk = current.sources.get("vk")
    if vk and vk.ok and vk.posts_last_week is not None:
        prev_vk = previous.sources.get("vk") if previous else None
        prev_posts = prev_vk.posts_last_week if (prev_vk and prev_vk.ok) else None
        if vk.posts_last_week > 0:
            trend = ""
            if prev_posts is not None and prev_posts != vk.posts_last_week:
                arrow = "↑" if vk.posts_last_week > prev_posts else "↓"
                trend = f" ({arrow} с {prev_posts} на прошлой неделе)"
            hint = ""
            if vk.latest_post_text:
                hint = f" — «{vk.latest_post_text[:80].strip()}…»"
            changes.append(DigestChange(
                name, VK_ACTIVITY,
                f"{name}: {vk.posts_last_week} постов{trend}{hint}",
                weight=base_weight + vk.posts_last_week,
            ))

    # ── Упоминания в СМИ → раздел ВАЖНО ──────────────────────────────
    for m in current.media_mentions:
        changes.append(DigestChange(
            name, MEDIA,
            f"[{name}] {m.get('title', '')} ({m.get('source', '')})",
            weight=base_weight,
        ))

    # ── Заметный всплеск активности high-приоритетного конкурента → ВАЖНО
    if competitor.priority == "high" and vk and vk.ok and (vk.posts_last_week or 0) >= 3:
        changes.append(DigestChange(
            name, IMPORTANT,
            f"{name} активно постит в VK ({vk.posts_last_week} постов за неделю) — вероятна PR-кампания",
            weight=base_weight + 50,
        ))

    return changes


def _build_recommendation(digest: Digest) -> str:
    """Простая rule-based рекомендация управляющему."""
    important = digest.by_category(IMPORTANT)
    vk = digest.by_category(VK_ACTIVITY)
    if important:
        top = important[0]
        return (
            f"На этой неделе выделяется активность: {top.competitor_name}. "
            "Рассмотрите ответный инфоповод — анонс вечера с живой музыкой на тот же период."
        )
    if vk:
        top = vk[0]
        return (
            f"{top.competitor_name} нарастил активность в VK. "
            "Держите ритм 2–3 качественных поста в неделю по контент-линиям Nuar (живая музыка, кухня, атмосфера)."
        )
    if digest.is_empty:
        return "Значимых изменений у конкурентов нет. Сфокусируйтесь на закрытии дыры по отзывам на Яндекс.Картах."
    return "Явных угроз нет. Поддерживайте плановую контент-активность и работу с отзывами."


def build_digest(
    competitors: list[Competitor],
    current_snapshots: dict[str, CompetitorSnapshot],
    repo: Repository,
    week_label: str,
    collected_at_iso: str,
) -> Digest:
    """Сравнивает свежие снимки с предыдущими из репозитория и собирает Digest."""
    digest = Digest(week_label=week_label)

    for comp in competitors:
        current = current_snapshots.get(comp.name)
        if current is None:
            continue
        # Считаем успешность источников для служебной строки
        for src in current.sources.values():
            if src.ok:
                digest.sources_ok += 1
            else:
                digest.sources_failed += 1

        previous = repo.latest_before(comp.name, collected_at_iso)
        digest.changes.extend(_compare_competitor(comp, current, previous))

    digest.recommendation = _build_recommendation(digest)
    return digest


def render_markdown(digest: Digest) -> str:
    """Рендерит Digest в текст для Telegram (Markdown)."""
    lines: list[str] = []
    lines.append("📊 *Еженедельный разведдайджест Nuar*")
    lines.append(f"Неделя: {digest.week_label}")
    lines.append("")

    def section(title: str, items: list[DigestChange]) -> None:
        if not items:
            return
        lines.append(title)
        for c in items:
            lines.append(f"• {c.text}")
        lines.append("")

    # ВАЖНО = события + упоминания в СМИ
    important = digest.by_category(IMPORTANT) + digest.by_category(MEDIA)
    section("🔴 *ВАЖНО*", important)
    section("📈 *ИЗМЕНЕНИЯ РЕЙТИНГОВ*", digest.by_category(RATING))
    section("📱 *АКТИВНОСТЬ В VK*", digest.by_category(VK_ACTIVITY))

    if digest.is_empty:
        lines.append("_За неделю значимых изменений не зафиксировано._")
        lines.append("")

    lines.append("💡 *РЕКОМЕНДАЦИЯ*")
    lines.append(digest.recommendation)

    # Служебная строка о полноте сбора
    if digest.sources_failed:
        lines.append("")
        lines.append(
            f"_Собрано источников: {digest.sources_ok}, недоступно: {digest.sources_failed}. "
            "Проверьте ссылки/токены в config и .env._"
        )

    return "\n".join(lines)


def send_digest(digest: Digest, repo: Repository, *, dry_run: bool = False) -> bool:
    """Рендерит и отправляет дайджест в Telegram. При dry_run — только печатает.
    Возвращает True при успешной отправке."""
    body = render_markdown(digest)
    if dry_run:
        preview = "\n" + "=" * 60 + "\n" + body + "\n" + "=" * 60 + "\n"
        try:
            print(preview)
        except UnicodeEncodeError:
            # Консоль не в UTF-8 — пишем байтами, не роняя прогон
            import sys
            sys.stdout.buffer.write(preview.encode("utf-8", errors="replace"))
        return True

    ok = send_message(body)
    repo.save_digest(digest.week_label, body, ok)
    if ok:
        log.info("Дайджест отправлен в Telegram")
    else:
        log.error("Не удалось отправить дайджест — см. настройки Telegram")
    return ok
