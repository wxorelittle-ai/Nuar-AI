"""Модель поста и справочники контента."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

# Сети публикации
NETWORKS = {"vk": "ВКонтакте", "telegram": "Telegram", "max": "MAX"}

# Контент-линии (бренд-гайд: «Мэтр приглашает»)
CONTENT_LINES = [
    "Живая музыка",
    "Кухня и шеф",
    "Атмосфера",
    "Событийность",
    "Гость",
    "Сезонное меню",
]

# Статусы поста в очереди
DRAFT = "draft"          # черновик, ждёт правки/утверждения
APPROVED = "approved"    # утверждён человеком, готов к публикации
PUBLISHED = "published"  # опубликован
FAILED = "failed"        # публикация не удалась после повторных попыток
STATUSES = {DRAFT: "Черновик", APPROVED: "Утверждён", PUBLISHED: "Опубликован", FAILED: "Ошибка"}


@dataclass
class Post:
    id: str
    network: str = "vk"
    content_line: str = ""
    topic: str = ""
    text: str = ""
    status: str = DRAFT
    created_at: str = ""          # ISO (проставляется снаружи)
    scheduled_at: str = ""        # ISO — время автопубликации (опционально)
    published_at: str = ""
    link: str = ""                # ссылка на опубликованный пост
    error: str = ""               # последняя ошибка публикации
    attempts: int = 0             # число неудачных попыток автопубликации

    def to_dict(self) -> dict:
        d = asdict(self)
        d["network_label"] = NETWORKS.get(self.network, self.network)
        d["status_label"] = STATUSES.get(self.status, self.status)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Post":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
