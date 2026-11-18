from datetime import datetime
from zoneinfo import ZoneInfo

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def now(cfg: dict) -> datetime:
    return datetime.now(ZoneInfo(cfg["place"]["timezone"]))


def describe(moment: datetime) -> str:
    return (
        f"{moment:%H:%M}, {WEEKDAYS[moment.weekday()]}, "
        f"{moment.day} {MONTHS[moment.month - 1]} {moment.year}"
    )


def spec(cfg: dict) -> dict:
    return {
        "name": "current_time",
        "description": "Текущие время, день недели и дата.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "run": lambda args: describe(now(cfg)),
    }
