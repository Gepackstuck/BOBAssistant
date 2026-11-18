import sqlite3
import time

from .config import ROOT

DB_PATH = ROOT / "data" / "memory.db"
MAX_FACTS = 60


class Memory:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE, created REAL NOT NULL)")
        self.db.commit()

    def remember(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "Нечего запоминать"
        self.db.execute("INSERT OR IGNORE INTO facts (text, created) VALUES (?, ?)", (text, time.time()))
        self.db.commit()
        return f"Запомнил: {text}"

    def forget(self, fragment: str) -> str:
        fragment = fragment.strip()
        if not fragment:
            return "Не сказано, что забыть"
        cursor = self.db.execute("DELETE FROM facts WHERE text LIKE ?", (f"%{fragment}%",))
        self.db.commit()
        return f"Забыл записей: {cursor.rowcount}"

    def facts(self) -> list[str]:
        rows = self.db.execute("SELECT text FROM facts ORDER BY created DESC LIMIT ?", (MAX_FACTS,)).fetchall()
        return [row[0] for row in reversed(rows)]


def specs(memory: Memory) -> list[dict]:
    return [
        {
            "name": "remember",
            "description": "Запомнить факт о пользователе или семье надолго, когда просят «запомни» или рассказывают о себе важное (имена, привычки, предпочтения). Пиши факт коротким законченным предложением.",
            "parameters": {
                "type": "object",
                "properties": {"fact": {"type": "string", "description": "Факт, например: Собаку зовут Бублик"}},
                "required": ["fact"],
                "additionalProperties": False,
            },
            "run": lambda args: memory.remember(args["fact"]),
        },
        {
            "name": "forget",
            "description": "Удалить запомненное, когда просят «забудь». Передай ключевое слово из факта.",
            "parameters": {
                "type": "object",
                "properties": {"fragment": {"type": "string", "description": "Слово или фраза из забываемого факта"}},
                "required": ["fragment"],
                "additionalProperties": False,
            },
            "run": lambda args: memory.forget(args["fragment"]),
        },
    ]
