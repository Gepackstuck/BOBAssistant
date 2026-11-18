import re
from datetime import date

import httpx

URL = "https://ru.wikipedia.org/w/api.php"
USER_AGENT = "BOBAssistant/0.1 github.com/Gepackstuck/BOBAssistant"
RESULTS = 2
EXTRACT_CHARS = 600
ACCENT = "́"
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
BIRTH_RE = re.compile(r"род\.\s+(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})")


def age_note(extract: str) -> str:
    match = BIRTH_RE.search(extract)
    if not match or re.search(r"\bум\.", extract[:match.end() + 80]):
        return ""
    day, month, year = int(match.group(1)), MONTHS.index(match.group(2)) + 1, int(match.group(3))
    today = date.today()
    years = today.year - year - ((today.month, today.day) < (month, day))
    return f" [Полных лет на сегодня: {years}]"


def lookup(query: str) -> str:
    response = httpx.get(
        URL,
        params={
            "action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrlimit": RESULTS,
            "prop": "extracts", "exintro": 1, "explaintext": 1, "exchars": EXTRACT_CHARS, "exlimit": RESULTS,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    pages = sorted(response.json().get("query", {}).get("pages", {}).values(), key=lambda page: page["index"])
    lines = [
        f"{page['title']}: {extract}{age_note(extract)}"
        for page in pages
        for extract in [page.get("extract", "").replace(ACCENT, "").replace(chr(10), " ")]
    ]
    return "\n".join(lines) if lines else "В энциклопедии ничего не найдено"


def spec() -> dict:
    return {
        "name": "encyclopedia",
        "description": "Энциклопедия (Википедия): кто такой человек, что это за место, термин или событие, когда родился, сколько лет, где находится, что значит. Вызывай на любой вопрос о фактах про человека, группу, место, фильм, песню или понятие, прежде чем отвечать. Для новостей и цен используй web_search.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Имя, название или термин по-русски, как в заголовке статьи, без вопросительных слов"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "run": lambda args: lookup(args["query"]),
    }
