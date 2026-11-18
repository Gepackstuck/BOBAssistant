import json
import re

from num2words import num2words

from .config import ROOT

USER_PATH = ROOT / "data" / "pronunciations.json"

BASE = {
    "madk1d": "мэдкид", "iphone": "айфон", "ipad": "айпад", "youtube": "ютуб", "google": "гугл",
    "wifi": "вайфай", "wi-fi": "вайфай", "hdmi": "эйч-ди-эм-ай", "usb": "ю-эс-би", "tv": "ти-ви",
    "ok": "окей", "okay": "окей", "dj": "ди-джей", "vpn": "ви-пи-эн", "led": "лэд", "ai": "эй-ай",
    "pc": "пи-си", "mac": "мак", "macbook": "макбук", "spotify": "спотифай", "wifi6": "вайфай шесть",
    "ps5": "пи-эс файв", "gb": "гигабайт", "mb": "мегабайт", "kinopoisk": "кинопоиск", "yandex": "яндекс",
}
LETTER_NAMES = {
    "a": "эй", "b": "би", "c": "си", "d": "ди", "e": "и", "f": "эф", "g": "джи", "h": "эйч", "i": "ай",
    "j": "джей", "k": "кей", "l": "эль", "m": "эм", "n": "эн", "o": "оу", "p": "пи", "q": "кью", "r": "ар",
    "s": "эс", "t": "ти", "u": "ю", "v": "ви", "w": "дабл-ю", "x": "экс", "y": "уай", "z": "зед",
}
DIGIT_NAMES = ["зиро", "ван", "ту", "сри", "фор", "файв", "сикс", "сэвен", "эйт", "найн"]
LEET = {"1": "i", "0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "$": "s", "@": "a"}
DIGRAPHS = [
    ("tion", "шн"), ("sch", "ск"), ("tch", "ч"), ("dge", "дж"), ("igh", "ай"), ("ough", "оф"),
    ("sh", "ш"), ("ch", "ч"), ("ph", "ф"), ("th", "т"), ("ck", "к"), ("qu", "кв"), ("wh", "в"),
    ("kn", "н"), ("wr", "р"), ("gh", ""), ("oo", "у"), ("ee", "и"), ("ea", "и"), ("ou", "ау"),
    ("ow", "оу"), ("oa", "оу"), ("ai", "эй"), ("ay", "эй"), ("ey", "эй"), ("oy", "ой"), ("oi", "ой"),
    ("au", "о"), ("aw", "о"), ("ie", "и"), ("ue", "ю"), ("ew", "ью"), ("eu", "ью"),
]
LETTERS = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х", "i": "и", "j": "дж",
    "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т",
    "u": "у", "v": "в", "w": "в", "x": "кс", "y": "и", "z": "з",
}
VOWELS = set("aeiouy")
LONG = {"a": "ей", "i": "ай", "o": "оу", "u": "ю"}
SILENT_E_RE = re.compile(r"^(.+?)([aiou])([bcdfgklmnprstvz])e$")
TOKEN_RE = re.compile(r"(?<!\w)(?=[A-Za-z0-9$@]*[A-Za-z])[A-Za-z0-9$@]+(?:[-'][A-Za-z0-9$@]+)*")
SEGMENT_RE = re.compile(r"\d+|[^\d]+")

_user_cache: tuple[float, dict] = (0.0, {})


def user_lexicon() -> dict:
    global _user_cache
    if not USER_PATH.exists():
        return {}
    modified = USER_PATH.stat().st_mtime
    if modified != _user_cache[0]:
        _user_cache = (modified, {key.lower(): value for key, value in json.loads(USER_PATH.read_text(encoding="utf-8")).items()})
    return _user_cache[1]


def collapse(text: str) -> str:
    return re.sub(r"(.)\1+", r"\1", text)


def word(text: str) -> str:
    silent = SILENT_E_RE.match(text)
    if silent:
        consonant = "s" if silent.group(3) == "c" else silent.group(3)
        return collapse(word(silent.group(1)) + LONG[silent.group(2)] + word(consonant))
    out, index = [], 0
    while index < len(text):
        for latin, cyrillic in DIGRAPHS:
            if text.startswith(latin, index):
                out.append(cyrillic)
                index += len(latin)
                break
        else:
            char = text[index]
            following = text[index + 1:index + 2]
            if char == "c" and following in ("e", "i", "y"):
                out.append("с")
            elif char == "e" and (index == 0 or text[index - 1] in VOWELS):
                out.append("э")
            elif char == "y" and index == 0:
                out.append("й")
            else:
                out.append(LETTERS.get(char, char))
            index += 1
    return collapse("".join(out))


def alphabetic(text: str) -> str:
    leet = "".join(
        LEET.get(char, char) if char in LEET and 0 < position < len(text) - 1 and text[position - 1].isalpha() and text[position + 1].isalpha() else char
        for position, char in enumerate(text)
    )
    return word(leet.lower())


def spell(text: str) -> str:
    return "-".join(LETTER_NAMES.get(char, char) for char in text.lower())


def part(text: str) -> str:
    if text.isalpha() and text.isupper() and (len(text) <= 2 or not set(text.lower()) & VOWELS):
        return spell(text)
    pieces = []
    segments = SEGMENT_RE.findall(text)
    for index, segment in enumerate(segments):
        if segment.isdigit():
            pieces.append(DIGIT_NAMES[int(segment)] if len(segment) == 1 else num2words(int(segment), lang="ru"))
        else:
            pieces.append(alphabetic(segment))
    return " ".join(piece for piece in pieces if piece)


def spoken(token: str) -> str:
    key = token.lower()
    for lexicon in (user_lexicon(), BASE):
        if key in lexicon:
            return lexicon[key]
    if re.search(r"[A-Za-z][013457$@][A-Za-z]", token):
        return alphabetic(token.replace("'", "").replace("-", " ")) if "-" not in token else " ".join(part(piece) for piece in token.split("-"))
    pieces = [piece for piece in re.split(r"[-']", token) if piece]
    return " ".join(part(piece) for piece in pieces)


def latin_to_speech(text: str) -> str:
    return TOKEN_RE.sub(lambda match: spoken(match.group(0)), text)
