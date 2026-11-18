from concurrent.futures import ThreadPoolExecutor

from ddgs import DDGS

TEXT_RESULTS = 4
NEWS_RESULTS = 4
BODY_LIMIT = 260
TIMEOUT = 12
OVERALL = 14


def attempt(call) -> list[dict]:
    try:
        return call() or []
    except Exception:
        return []


def settled(job) -> list[dict]:
    try:
        return job.result(timeout=OVERALL)
    except Exception:
        return []


def search(query: str) -> str:
    client = DDGS(timeout=TIMEOUT)
    with ThreadPoolExecutor(max_workers=2) as pool:
        news_job = pool.submit(attempt, lambda: client.news(query, region="ru-ru", max_results=NEWS_RESULTS))
        text_job = pool.submit(attempt, lambda: client.text(query, region="ru-ru", max_results=TEXT_RESULTS))
        news = settled(news_job)
        text = settled(text_job)
    lines = [
        f"[{item.get('date', '')[:10]}] {item['title']}: {item.get('body', '')[:BODY_LIMIT]}"
        for item in news
    ] + [f"{item['title']}: {item.get('body', '')[:BODY_LIMIT]}" for item in text]
    return "\n".join(lines) if lines else "Ничего не найдено"


def spec() -> dict:
    return {
        "name": "web_search",
        "description": "Поиск в интернете и по новостям. Используй для свежих фактов: новости, курсы валют, результаты матчей, цены, кто сейчас занимает должность. Для справок о людях, местах и понятиях есть encyclopedia, для погоды, времени и расчётов не нужен.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Поисковый запрос по-русски"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "run": lambda args: search(args["query"]),
    }
