"""Метаданные каналов публикации для UI настроек."""
from __future__ import annotations

CHANNELS = [
    {
        "key": "vk",
        "title": "ВКонтакте",
        "subtitle": "публикация на стену сообщества",
        "docs": "https://dev.vk.com/ru/method/wall.post",
        "help": "Нужен ключ доступа сообщества с правами «Управление» и «Стена», "
                "и числовой id сообщества. Токен создаётся в настройках сообщества → «Работа с API».",
        "fields": [
            {"name": "access_token", "label": "Ключ доступа сообщества", "type": "password", "placeholder": "vk1.a.…"},
            {"name": "group_id", "label": "ID сообщества (число)", "type": "text", "placeholder": "123456789",
             "hint": "Только число, без минуса. Узнать: regvk.com/id или vk.com/club<ID>."},
        ],
    },
    {
        "key": "telegram",
        "title": "Telegram",
        "subtitle": "публикация в канал",
        "docs": "https://core.telegram.org/bots/api#sendmessage",
        "help": "Создайте бота у @BotFather, добавьте его администратором в свой канал. "
                "Укажите токен бота и канал (@username или числовой chat_id). "
                "Если сервер не пропускает Telegram — впишите прокси.",
        "fields": [
            {"name": "bot_token", "label": "Токен бота", "type": "password", "placeholder": "1234567:AA…"},
            {"name": "channel", "label": "Канал", "type": "text", "placeholder": "@my_restaurant",
             "hint": "@username публичного канала или chat_id вида -100…"},
            {"name": "proxy", "label": "Прокси (если Telegram заблокирован)", "type": "text",
             "placeholder": "http://user:pass@host:port",
             "hint": "Необязательно. http://…, https://… или socks5://… "
                     "Оставьте пустым, если сервер и так видит api.telegram.org."},
        ],
    },
    {
        "key": "max",
        "title": "MAX",
        "subtitle": "публикация в канал/чат",
        "docs": "https://dev.max.ru/docs-api",
        "help": "Создайте бота у @MasterBot (команда /create), добавьте его в свой "
                "канал/чат. Укажите токен бота и числовой chat_id. MAX доступен из РФ "
                "без прокси. Публикация ботов — только для верифицированных юрлиц РФ.",
        "fields": [
            {"name": "access_token", "label": "Токен бота", "type": "password", "placeholder": "…"},
            {"name": "chat_id", "label": "chat_id канала/чата (число)", "type": "text", "placeholder": "-70000000…",
             "hint": "Числовой id чата/канала, куда добавлен бот."},
        ],
    },
]

CHANNEL_BY_KEY = {c["key"]: c for c in CHANNELS}

# Публикаторы по ключу канала (ленивая привязка, чтобы избежать циклов импорта)
def get_publisher(key: str):
    from . import vk, telegram, max as max_pub
    return {"vk": vk, "telegram": telegram, "max": max_pub}.get(key)
