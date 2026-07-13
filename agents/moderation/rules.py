"""Rule-based проверки поста. Чистые функции, тестируются без сети.

Уровни:
  • block — жёсткое нарушение, публикацию не пропускаем;
  • warn  — предупреждение, публиковать можно, но стоит взглянуть.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

BLOCK = "block"
WARN = "warn"


@dataclass
class Issue:
    level: str      # block | warn
    code: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


# ── Скидки и ценовое давление — запрещены (премиум-позиционирование) ──
PRICE_PATTERNS = [
    (r"скидк", "скидка"),
    (r"распродаж", "распродажа"),
    (r"промокод", "промокод"),
    (r"\bакци[яию]\b", "акция"),
    (r"-?\d{1,3}\s?%", "процент/скидка"),
    (r"спецпредложен", "спецпредложение"),
    (r"по\s+спеццен", "спеццена"),
    (r"бесплатн", "«бесплатно»"),
    (r"дешёв|дешев", "«дёшево»"),
    (r"\bхаляв", "«халява»"),
]

# Максимальная длина текста по сети
MAX_LEN = {"telegram": 4096, "vk": 16000}

# Эмодзи (основные блоки) — бренд: без эмодзи
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️⭐⭕]"
)
CAPS_RE = re.compile(r"\b[А-ЯЁ]{4,}\b")


def check(text: str, network: str = "vk") -> list[Issue]:
    issues: list[Issue] = []
    t = (text or "").strip()

    if not t:
        return [Issue(BLOCK, "empty", "Пустой текст поста")]

    low = t.lower()

    # Скидки / ценовое давление → block
    for pattern, human in PRICE_PATTERNS:
        if re.search(pattern, low):
            issues.append(Issue(
                BLOCK, "price",
                f"Обнаружено ценовое давление ({human}). Для премиум-сегмента скидки и акции запрещены."))
            break  # одного упоминания достаточно

    # Длина под сеть → block, если превышает лимит
    limit = MAX_LEN.get(network, MAX_LEN["vk"])
    if len(t) > limit:
        issues.append(Issue(BLOCK, "too_long",
                            f"Текст {len(t)} символов — больше лимита {network} ({limit})."))

    # Эмодзи → warn
    if EMOJI_RE.search(t):
        issues.append(Issue(WARN, "emoji", "В тексте есть эмодзи — бренд предполагает сдержанный стиль без них."))

    # Восклицания → warn
    if t.count("!") >= 2 or "!!!" in t:
        issues.append(Issue(WARN, "exclaim", "Много восклицательных знаков — тон стоит сделать спокойнее."))

    # КАПС → warn
    caps = CAPS_RE.findall(t)
    if caps:
        issues.append(Issue(WARN, "caps", f"Слова капсом ({', '.join(caps[:3])}) — читается как крик."))

    # Слишком короткий → warn
    if len(t) < 30:
        issues.append(Issue(WARN, "too_short", "Пост очень короткий — возможно, стоит раскрыть мысль."))

    return issues
