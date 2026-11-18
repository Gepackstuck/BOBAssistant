import random
import re
import sys
from pathlib import Path

import httpx

TOPICS = [
    "кухня и готовка", "дети и школа", "работа и офис", "футбол", "фильмы и сериалы", "погода",
    "покупки", "ремонт квартиры", "путешествия", "машины", "здоровье", "домашние животные",
    "деньги и банки", "новости", "музыка", "компьютеры", "дача и огород", "праздники",
    "спор супругов", "телефонный разговор", "реклама по телевизору", "диалог из боевика",
    "мультфильм для детей", "ток-шоу", "прогноз погоды по ТВ", "спортивный комментатор",
]
PROMPT = (
    "Напиши 40 разных реплик на русском языке, которые люди произносят вслух дома или звучат по телевизору. "
    "Тема: {topic}. Реплики разной длины, от двух до пятнадцати слов, разговорные, с именами и числами словами. "
    "Не используй слова «Боб», «миньон», «подручный», «Сбер». Каждая реплика с новой строки, без нумерации."
)
BANNED = re.compile(r"боб|минь?он|подручн|сбер", re.IGNORECASE)


def main(target: Path, count: int) -> None:
    client = httpx.Client(base_url="http://localhost:11434/v1", timeout=300)
    lines: set[str] = set(target.read_text(encoding="utf-8").splitlines()) if target.exists() else set()
    rng = random.Random(len(lines))
    while len(lines) < count:
        topic = rng.choice(TOPICS)
        response = client.post("/chat/completions", json={
            "model": "qwen3:30b-instruct",
            "messages": [{"role": "user", "content": PROMPT.format(topic=topic)}],
            "temperature": 1.0,
            "max_tokens": 2000,
        })
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        fresh = {
            clean
            for raw in text.splitlines()
            for clean in [re.sub(r"^[\s\-–—*\d.)]+", "", raw).strip().strip("«»\"")]
            if 2 <= len(clean.split()) <= 20 and not BANNED.search(clean)
        }
        lines |= fresh
        target.write_text("\n".join(sorted(lines)), encoding="utf-8")
        print(f"{topic}: +{len(fresh)}, всего {len(lines)}", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), int(sys.argv[2]))
