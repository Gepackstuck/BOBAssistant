import functools
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
GEOCODER = "https://nominatim.openstreetmap.org/search"
USER_AGENT ="BOBAssistant/0.1 github.com/Gepackstuck/BOBAssistant"

SYMBOLS = [
    ("heavysleet", "сильный мокрый снег"),
    ("lightsleet", "небольшой мокрый снег"),
    ("sleet", "мокрый снег"),
    ("heavysnow", "сильный снег"),
    ("lightsnow", "небольшой снег"),
    ("snow", "снег"),
    ("heavyrain", "сильный дождь"),
    ("lightrain", "небольшой дождь"),
    ("rain", "дождь"),
    ("thunder", "гроза"),
    ("fog", "туман"),
    ("partlycloudy", "переменная облачность"),
    ("cloudy", "облачно"),
    ("fair", "малооблачно"),
    ("clearsky", "ясно"),
]


def symbol_text(code: str | None) -> str:
    if not code:
        return "без данных об осадках"
    base = code.split("_")[0]
    return next((text for key, text in SYMBOLS if key in base), base)


def fetch(lat: float, lon: float) -> list[dict]:
    response = httpx.get(
        URL,
        params={"lat": round(lat, 2), "lon": round(lon, 2)},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["properties"]["timeseries"]


def day_summary(series: list[dict], tz: ZoneInfo, day: datetime) -> str | None:
    points = [
        p for p in series
        if datetime.fromisoformat(p["time"]).astimezone(tz).date() == day.date()
    ]
    if not points:
        return None
    temps = [p["data"]["instant"]["details"]["air_temperature"] for p in points]
    periods = [p["data"].get("next_1_hours") or p["data"].get("next_6_hours") or {} for p in points]
    hourly = [p["data"]["next_1_hours"] for p in points if p["data"].get("next_1_hours")]
    amounts = hourly or [p["data"]["next_6_hours"] for p in points[::6] if p["data"].get("next_6_hours")]
    total = sum(a.get("details", {}).get("precipitation_amount", 0) for a in amounts)
    codes = [period.get("summary", {}).get("symbol_code", "") for period in periods]
    worst = min(
        (rank for rank, (key, _) in enumerate(SYMBOLS) for code in codes if key in code.split("_")[0]),
        default=None,
    )
    sky = SYMBOLS[worst][1] if worst is not None else "без данных"
    rain = f"осадки {round(total, 1)} мм" if total >= 0.1 else "осадков нет"
    return f"от {round(min(temps))} до {round(max(temps))} °C, {sky}, {rain}"


@functools.lru_cache(maxsize=128)
def geocode(city: str) -> dict | None:
    response = httpx.get(
        GEOCODER,
        params={"q": city, "format": "json", "limit": 1, "accept-language": "ru"},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    found = response.json()
    if not found:
        return None
    return {
        "name": found[0]["display_name"].split(",")[0],
        "latitude": float(found[0]["lat"]),
        "longitude": float(found[0]["lon"]),
    }


def report(cfg: dict, city: str | None = None) -> str:
    place = cfg["place"]
    if city:
        found = geocode(city.strip())
        if found is None:
            return f"Город «{city}» не найден"
        place = {**place, **found}
    if place.get("latitude") is None:
        return "Место не настроено: задайте place.latitude и place.longitude в config.local.yaml"
    tz = ZoneInfo(place["timezone"])
    series = fetch(place["latitude"], place["longitude"])
    current = series[0]["data"]
    temp = current["instant"]["details"]["air_temperature"]
    wind = current["instant"]["details"].get("wind_speed")
    next_hour = current.get("next_1_hours") or current.get("next_6_hours") or {}
    precipitation = next_hour.get("details", {}).get("precipitation_amount")
    today = datetime.now(tz)
    rest_of_today = day_summary(series, tz, today)
    parts = [
        f"{place.get('name') or 'Здесь'}: сейчас {round(temp)} °C, {symbol_text(next_hour.get('summary', {}).get('symbol_code'))}",
        f"ветер {round(wind)} м/с" if wind is not None else None,
        f"осадки в ближайший час {precipitation} мм" if precipitation else None,
        f"сегодня {rest_of_today}" if rest_of_today else None,
        f"завтра {day_summary(series, tz, today + timedelta(days=1))}",
        f"послезавтра {day_summary(series, tz, today + timedelta(days=2))}",
    ]
    return "; ".join(part for part in parts if part)


def spec(cfg: dict) -> dict:
    return {
        "name": "weather",
        "description": "Погода сейчас и прогноз на сегодня, завтра и послезавтра (met.no). Без города — дома у пользователя.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "Город, если спрашивают не про дом"}},
            "additionalProperties": False,
        },
        "run": lambda args: report(cfg, args.get("city")),
    }
