"""Погода по городу заведения — локальный сигнал формата вечера.

Источник: Open-Meteo (open-meteo.com) — бесплатно, без ключей, с любого IP.
  • геокодинг:  https://geocoding-api.open-meteo.com/v1/search
  • прогноз:    https://api.open-meteo.com/v1/forecast (до 16 дней)

Зачем управляющему: погода решает формат. Гроза в день open-air джема — это
не «интересный факт», а повод перенести вечер в зал за неделю до даты.

ВАЖНО: несуществующий город геокодер отдаёт как HTTP 200 БЕЗ ключа "results"
(не 404) — проверять наличие результатов, а не код ответа.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, asdict

import httpx

log = logging.getLogger("restopulse.weather")

GEO_API = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
UA = {"User-Agent": "METR/0.1 (restaurant analytics)"}
TIMEOUT = 20
FORECAST_DAYS = 16

# Прогноз меняется — держим недолго. Геокод города стабилен — держим долго.
FORECAST_TTL = 3 * 3600
GEO_TTL = 30 * 24 * 3600

_LOCK = threading.Lock()
_geo_cache: dict[str, tuple[float, object]] = {}
_forecast_cache: dict[str, tuple[float, object]] = {}


# ── Коды погоды WMO → человеческое описание ───────────────────────────
WMO = {
    0: "ясно", 1: "малооблачно", 2: "переменная облачность", 3: "пасмурно",
    45: "туман", 48: "изморозь",
    51: "морось", 53: "морось", 55: "сильная морось",
    56: "ледяная морось", 57: "ледяная морось",
    61: "небольшой дождь", 63: "дождь", 65: "сильный дождь",
    66: "ледяной дождь", 67: "ледяной дождь",
    71: "небольшой снег", 73: "снег", 75: "сильный снег", 77: "снежная крупа",
    80: "ливень", 81: "ливень", 82: "сильный ливень",
    85: "снегопад", 86: "сильный снегопад",
    95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом",
}

WET = set(range(51, 68)) | set(range(80, 87)) | {95, 96, 99}
STORM = {95, 96, 99, 82}


@dataclass
class DayWeather:
    date: str
    code: int = 0
    condition: str = ""
    tmin: float = 0.0
    tmax: float = 0.0
    precip: float = 0.0        # мм
    wind: float = 0.0          # км/ч
    advice: str = ""           # что это значит для формата вечера
    outdoor_ok: bool = True    # сработает ли открытая площадка

    def to_dict(self) -> dict:
        return asdict(self)


def advice_for(code: int, tmax: float, precip: float, wind: float) -> tuple[str, bool]:
    """Совет по формату вечера + пригодность открытой площадки."""
    if code in STORM or precip >= 10:
        return ("гроза и сильные осадки — открытая площадка отпадает, "
                "переносите в зал и скажите об этом в анонсе"), False
    if code in WET or precip >= 1:
        return ("дождь — ставка на камерный зал: приглушённый свет, "
                "горячие напитки, живая музыка"), False
    if tmax >= 30:
        return "жара — лёгкие коктейли и поздний старт, до заката гостей мало", True
    if tmax >= 22:
        return "тепло и сухо — веранда и open-air работают, можно вынести сет на улицу", True
    if tmax <= 5:
        return "холодно — тёплый зал, крепкие и горячие напитки", False
    if wind >= 30:
        return "сильный ветер — открытая площадка некомфортна", False
    return "погода нейтральная — формат выбирайте по программе, а не по небу", True


def _cached(cache: dict, key: str, ttl: float):
    hit = cache.get(key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    return None


def geocode(city: str) -> dict | None:
    """(lat, lon, tz, name) города или None. Кэш — на месяц."""
    city = (city or "").strip()
    if not city:
        return None
    cached = _cached(_geo_cache, city.lower(), GEO_TTL)
    if cached is not None:
        return cached or None
    try:
        r = httpx.get(GEO_API, headers=UA, timeout=TIMEOUT,
                      params={"name": city, "count": 1, "language": "ru", "format": "json"})
    except httpx.HTTPError as exc:
        log.warning("Геокодер недоступен (%s): %s", city, exc)
        return None
    if r.status_code != 200:
        return None
    # несуществующий город → 200 без "results"
    results = r.json().get("results") or []
    if not results:
        log.info("Город не найден геокодером: %s", city)
        with _LOCK:
            _geo_cache[city.lower()] = (time.time(), {})   # не долбить API повторно
        return None
    top = results[0]
    out = {"lat": top["latitude"], "lon": top["longitude"],
           "tz": top.get("timezone", "auto"), "name": top.get("name", city)}
    with _LOCK:
        _geo_cache[city.lower()] = (time.time(), out)
    return out


def parse_forecast(payload: dict) -> list[DayWeather]:
    """Чистый разбор ответа Open-Meteo (тестируется без сети)."""
    daily = payload.get("daily") or {}
    days = daily.get("time") or []
    out: list[DayWeather] = []
    for i, day in enumerate(days):
        def val(key, default=0.0):
            arr = daily.get(key) or []
            v = arr[i] if i < len(arr) else default
            return default if v is None else v

        code = int(val("weather_code", 0))
        tmax = float(val("temperature_2m_max"))
        precip = float(val("precipitation_sum"))
        wind = float(val("wind_speed_10m_max"))
        adv, outdoor = advice_for(code, tmax, precip, wind)
        out.append(DayWeather(
            date=day, code=code, condition=WMO.get(code, "—"),
            tmin=float(val("temperature_2m_min")), tmax=tmax,
            precip=precip, wind=wind, advice=adv, outdoor_ok=outdoor))
    return out


def forecast(city: str) -> list[DayWeather]:
    """Прогноз на 16 дней. Пустой список — если город не найден или API молчит."""
    cached = _cached(_forecast_cache, (city or "").lower(), FORECAST_TTL)
    if cached is not None:
        return cached
    loc = geocode(city)
    if not loc:
        return []
    try:
        r = httpx.get(FORECAST_API, headers=UA, timeout=TIMEOUT, params={
            "latitude": loc["lat"], "longitude": loc["lon"],
            "daily": ("weather_code,temperature_2m_max,temperature_2m_min,"
                      "precipitation_sum,wind_speed_10m_max"),
            "timezone": loc["tz"], "forecast_days": FORECAST_DAYS})
    except httpx.HTTPError as exc:
        log.warning("Прогноз недоступен (%s): %s", city, exc)
        return []
    if r.status_code != 200:
        log.warning("Прогноз HTTP %s (%s)", r.status_code, city)
        return []
    days = parse_forecast(r.json())
    with _LOCK:
        _forecast_cache[(city or "").lower()] = (time.time(), days)
    return days


def for_date(city: str, iso_date: str) -> DayWeather | None:
    """Погода на конкретную дату, если она попадает в окно прогноза."""
    for d in forecast(city):
        if d.date == iso_date:
            return d
    return None
