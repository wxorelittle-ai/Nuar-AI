"""Сервис модерации: rule-based проверки + опциональная AI-проверка тона."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import rules
from .rules import Issue, BLOCK, WARN

log = logging.getLogger("restopulse.moderation")


@dataclass
class ModerationResult:
    ok: bool = True                 # нет block-нарушений
    level: str = "ok"               # ok | warn | block
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "level": self.level,
                "issues": [i.to_dict() for i in self.issues]}


class ModerationError(Exception):
    """Публикация заблокирована модерацией."""
    def __init__(self, result: ModerationResult):
        self.result = result
        super().__init__("Публикация заблокирована модерацией")


def moderate(text: str, network: str = "vk", *, use_llm: bool = False) -> ModerationResult:
    issues = rules.check(text, network)

    # Опциональная проверка тона активной моделью (только советы, не блокирует)
    if use_llm:
        try:
            issues += _llm_review(text)
        except Exception as exc:  # AI недоступен — не мешаем rule-based модерации
            log.debug("AI-проверка тона недоступна: %s", exc)

    has_block = any(i.level == BLOCK for i in issues)
    has_warn = any(i.level == WARN for i in issues)
    level = BLOCK if has_block else (WARN if has_warn else "ok")
    return ModerationResult(ok=not has_block, level=level, issues=issues)


def _llm_review(text: str) -> list[Issue]:
    """Просит активную модель отметить нарушения тона бренда. Advisory (warn)."""
    from agents.llm.base import ChatMessage
    from agents.llm import service as llm

    system = (
        "Ты — редактор премиального ресторана. Проверь пост на соответствие тону: "
        "сдержанность, без скидок и ценового давления, без канцелярита и кликбейта. "
        "Если всё хорошо — ответь ровно OK. Если есть замечание — одной короткой фразой."
    )
    verdict = llm.chat([ChatMessage("system", system), ChatMessage("user", text)],
                       temperature=0.0, max_tokens=120).strip()
    if verdict.upper().startswith("OK") or not verdict:
        return []
    return [Issue(WARN, "tone_ai", f"Замечание ассистента по тону: {verdict}")]
