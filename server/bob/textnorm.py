import re

from num2words import num2words

UNITS = {
    "°": ("градус", "градуса", "градусов"),
    "%": ("процент", "процента", "процентов"),
}

NUMBER_UNIT_RE = re.compile(r"([-−–]?\d+(?:[.,]\d+)?)\s*(°\s*[CС]?|%)")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
NUMBER_RE = re.compile(r"[-−–]?\d+(?:[.,]\d+)?")
MARKUP_RE = re.compile(r"[*_#`>]+")


def plural(n: float, forms: tuple[str, str, str]) -> str:
    if n != int(n):
        return forms[1]
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def to_number(raw: str) -> float:
    value = float(raw.replace(",", ".").replace("−", "-").replace("–", "-"))
    return int(value) if value == int(value) else value


def say_number(raw: str) -> str:
    return num2words(to_number(raw), lang="ru")


def say_time(match: re.Match) -> str:
    hours, minutes = int(match.group(1)), int(match.group(2))
    hours_text = num2words(hours, lang="ru")
    if minutes == 0:
        return f"{hours_text} ноль ноль"
    minutes_text = num2words(minutes, lang="ru")
    return f"{hours_text} {'ноль ' if minutes < 10 else ''}{minutes_text}"


def say_number_unit(match: re.Match) -> str:
    value = to_number(match.group(1))
    unit = UNITS["%" if match.group(2) == "%" else "°"]
    return f"{say_number(match.group(1))} {plural(value, unit)}"


def for_speech(text: str) -> str:
    text = MARKUP_RE.sub("", text)
    text = TIME_RE.sub(say_time, text)
    text = NUMBER_UNIT_RE.sub(say_number_unit, text)
    text = NUMBER_RE.sub(lambda m: say_number(m.group(0)), text)
    return re.sub(r"\s+", " ", text).strip()
