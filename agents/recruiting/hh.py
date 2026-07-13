"""Клиент HeadHunter API (dev.hh.ru).

Публичные эндпоинты без авторизации: поиск вакансий и подсказка региона.
Чистые build/parse-функции тестируются без сети; fetch_* ходят в сеть.
HH требует осмысленный User-Agent.
"""
from __future__ import annotations

import logging
import statistics
import time
from collections import Counter

import httpx

from config.settings import settings
from .models import Vacancy, RoleMarket

log = logging.getLogger("restopulse.recruiting.hh")

API = "https://api.hh.ru"
OAUTH = "https://hh.ru/oauth/token"
TIMEOUT = 20

# Кэш токена приложения HH (client_credentials)
_token_cache = {"value": None, "exp": 0.0}


def _app_token() -> str | None:
    """Токен приложения HH (если заданы HH_CLIENT_ID/HH_CLIENT_SECRET).
    Нужен, потому что HH закрыл анонимный поиск вакансий (403)."""
    cid, csec = settings.hh_client_id, settings.hh_client_secret
    if not (cid and csec):
        return None
    now = time.time()
    if _token_cache["value"] and _token_cache["exp"] > now + 60:
        return _token_cache["value"]
    try:
        r = httpx.post(OAUTH, data={"grant_type": "client_credentials",
                                    "client_id": cid, "client_secret": csec}, timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            _token_cache["value"] = d.get("access_token")
            _token_cache["exp"] = now + int(d.get("expires_in", 1209600))
            return _token_cache["value"]
        log.warning("HH oauth HTTP %s: %s", r.status_code, r.text[:160])
    except httpx.HTTPError as exc:
        log.warning("HH oauth недоступен: %s", exc)
    return None

# Запасные area_id, если подсказка не сработает
AREA_FALLBACK = {
    "тюмень": "95", "москва": "1", "санкт-петербург": "2", "спб": "2",
    "екатеринбург": "3", "новосибирск": "4", "казань": "88",
}


def _headers() -> dict:
    h = {"User-Agent": "METR-recruiting/0.1 (restaurant analytics)",
         "Accept": "application/json"}
    token = _app_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ── Регион ────────────────────────────────────────────────────────────
def suggest_area(city: str) -> str | None:
    city = (city or "").strip()
    if not city:
        return None
    try:
        r = httpx.get(f"{API}/suggests/areas", params={"text": city},
                      headers=_headers(), timeout=TIMEOUT)
        if r.status_code == 200:
            for item in r.json().get("items", []):
                if item.get("text", "").lower().startswith(city.lower()):
                    return str(item.get("id"))
    except httpx.HTTPError as exc:
        log.warning("HH suggests/areas недоступен: %s", exc)
    return AREA_FALLBACK.get(city.lower())


# ── Вакансии ──────────────────────────────────────────────────────────
def build_vacancies_request(text: str, area: str | None, per_page: int = 100):
    params = {"text": text, "per_page": min(per_page, 100), "order_by": "publication_time"}
    if area:
        params["area"] = area
    return f"{API}/vacancies", params


def parse_vacancies(data: dict) -> tuple[int, list[Vacancy]]:
    found = int(data.get("found", 0) or 0)
    out: list[Vacancy] = []
    for it in data.get("items", []):
        sal = it.get("salary") or {}
        out.append(Vacancy(
            name=it.get("name", ""),
            employer=(it.get("employer") or {}).get("name", ""),
            salary_from=sal.get("from"), salary_to=sal.get("to"),
            currency=sal.get("currency"), gross=sal.get("gross"),
            area=(it.get("area") or {}).get("name", ""),
            url=it.get("alternate_url", ""),
            published_at=it.get("published_at", ""),
        ))
    return found, out


def fetch_vacancies(text: str, area: str | None, per_page: int = 100) -> tuple[int, list[Vacancy], str]:
    """Возвращает (found, vacancies, status). status: ok | forbidden | error."""
    url, params = build_vacancies_request(text, area, per_page)
    try:
        r = httpx.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        log.warning("HH vacancies недоступен (%s): %s", text, exc)
        return 0, [], "error"
    if r.status_code == 403:
        return 0, [], "forbidden"
    if r.status_code != 200:
        log.warning("HH vacancies HTTP %s (%s)", r.status_code, text)
        return 0, [], "error"
    found, vacs = parse_vacancies(r.json())
    return found, vacs, "ok"


# ── Аналитика ─────────────────────────────────────────────────────────
def salary_points(vacancies: list[Vacancy]) -> list[float]:
    """Зарплаты «на руки» (RUR). gross → net ≈ ×0.87 (минус НДФЛ 13%)."""
    pts: list[float] = []
    for v in vacancies:
        if v.currency and v.currency != "RUR":
            continue
        vals = [x for x in (v.salary_from, v.salary_to) if x]
        if not vals:
            continue
        val = sum(vals) / len(vals)
        if v.gross:
            val *= 0.87
        pts.append(val)
    return pts


def _pctl(sorted_vals: list[float], q: float) -> int:
    if not sorted_vals:
        return 0
    idx = min(int(q * (len(sorted_vals) - 1) + 0.5), len(sorted_vals) - 1)
    return int(round(sorted_vals[idx] / 100) * 100)


def top_employers(vacancies: list[Vacancy], n: int = 5) -> list[dict]:
    counter = Counter(v.employer for v in vacancies if v.employer)
    return [{"name": name, "count": cnt} for name, cnt in counter.most_common(n)]


def role_market(role: str, vacancies: list[Vacancy], found: int) -> RoleMarket:
    pts = sorted(salary_points(vacancies))
    rm = RoleMarket(role=role, found=found, with_salary=len(pts),
                    top_employers=top_employers(vacancies))
    if pts:
        rm.salary_median = int(round(statistics.median(pts) / 100) * 100)
        rm.salary_p25 = _pctl(pts, 0.25)
        rm.salary_p75 = _pctl(pts, 0.75)
    return rm
