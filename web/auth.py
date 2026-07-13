"""Авторизация в панель МЭТР.

Простой вход по паролю администратора (ADMIN_PASSWORD). Сессия — подписанная
HMAC cookie с TTL. Секрет берётся из SECRET_KEY или генерируется и хранится в
data/.secret (переживает перезапуск).

Если ADMIN_PASSWORD не задан — авторизация ВЫКЛЮЧЕНА (режим локальной разработки),
о чём приложение предупреждает в логах. На сервере пароль задавать обязательно.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time

from config.settings import settings, DATA_DIR

log = logging.getLogger("restopulse.auth")

COOKIE = "metr_session"
TTL = 7 * 24 * 3600  # 7 дней


def _secret() -> bytes:
    if settings.secret_key:
        return settings.secret_key.encode("utf-8")
    path = DATA_DIR / ".secret"
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = os.urandom(32)
    path.write_bytes(secret)
    return secret


def auth_enabled() -> bool:
    return bool(settings.admin_password)


def check_password(password: str) -> bool:
    if not settings.admin_password:
        return False
    return hmac.compare_digest(password or "", settings.admin_password)


def make_token() -> str:
    exp = str(int(time.time()) + TTL)
    sig = base64.urlsafe_b64encode(
        hmac.new(_secret(), exp.encode(), hashlib.sha256).digest()).decode()
    return f"{exp}.{sig}"


def valid_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    exp_s, sig = token.split(".", 1)
    try:
        if int(exp_s) < time.time():
            return False
    except ValueError:
        return False
    good = base64.urlsafe_b64encode(
        hmac.new(_secret(), exp_s.encode(), hashlib.sha256).digest()).decode()
    return hmac.compare_digest(sig, good)


def is_authed(request) -> bool:
    if not auth_enabled():
        return True  # пароль не задан — вход открыт (локальный режим)
    return valid_token(request.cookies.get(COOKIE))
