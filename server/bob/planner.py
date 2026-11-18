import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .config import ROOT
from .textnorm import plural
from .tools.clock import now

DB_PATH = ROOT / "data" / "planner.db"
MISSED_LIMIT = 3600
KIND_WORDS = {"timer": "таймер", "reminder": "напоминание", "alarm": "будильник"}
UNITS = {"секунд": ("секунду", "секунды", "секунд"), "минут": ("минуту", "минуты", "минут"), "часов": ("час", "часа", "часов")}


@dataclass
class Entry:
    id: int
    device: str
    kind: str
    fire_at: float
    text: str
    repeat: str


def duration_words(seconds: int) -> str:
    parts = []
    for name, size in (("часов", 3600), ("минут", 60), ("секунд", 1)):
        amount, seconds = divmod(seconds, size)
        if amount:
            parts.append(f"{amount} {plural(amount, UNITS[name])}")
    return " ".join(parts) or "0 секунд"


class Planner:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS schedule (id INTEGER PRIMARY KEY, device TEXT NOT NULL, kind TEXT NOT NULL, fire_at REAL NOT NULL, text TEXT NOT NULL, repeat TEXT NOT NULL DEFAULT '')")
        self.db.execute("CREATE TABLE IF NOT EXISTS shopping (id INTEGER PRIMARY KEY, item TEXT NOT NULL UNIQUE COLLATE NOCASE)")
        self.db.commit()
        self.lock = threading.RLock()
        self.on_fire: Callable[[Entry], None] | None = None

    def start(self) -> None:
        threading.Thread(target=self.loop, daemon=True, name="planner").start()

    def loop(self) -> None:
        while True:
            for entry in self.due():
                if self.on_fire:
                    try:
                        self.on_fire(entry)
                    except Exception as error:
                        print(f"[планировщик] {error}", flush=True)
            time.sleep(1)

    def due(self) -> list[Entry]:
        current = time.time()
        with self.lock:
            rows = self.db.execute("SELECT id, device, kind, fire_at, text, repeat FROM schedule WHERE fire_at <= ? ORDER BY fire_at", (current,)).fetchall()
            fired = []
            for row in rows:
                entry = Entry(*row)
                if entry.repeat == "daily":
                    next_at = entry.fire_at
                    while next_at <= current:
                        next_at += 86400
                    self.db.execute("UPDATE schedule SET fire_at = ? WHERE id = ?", (next_at, entry.id))
                else:
                    self.db.execute("DELETE FROM schedule WHERE id = ?", (entry.id,))
                if current - entry.fire_at <= MISSED_LIMIT:
                    fired.append(entry)
            self.db.commit()
        return fired

    def add(self, device: str, kind: str, fire_at: float, text: str, repeat: str = "") -> Entry:
        with self.lock:
            cursor = self.db.execute("INSERT INTO schedule (device, kind, fire_at, text, repeat) VALUES (?, ?, ?, ?, ?)", (device, kind, fire_at, text, repeat))
            self.db.commit()
        return Entry(cursor.lastrowid, device, kind, fire_at, text, repeat)

    def timer(self, device: str, seconds: int, label: str = "") -> str:
        if seconds <= 0:
            raise ValueError("время таймера должно быть больше нуля")
        span = duration_words(seconds)
        self.add(device, "timer", time.time() + seconds, label or f"на {span}")
        return f"Таймер {('«' + label + '» ') if label else ''}на {span} поставлен."

    def reminder(self, device: str, text: str, in_minutes: float | None = None, at: str | None = None) -> str:
        if in_minutes is not None:
            moment = now(self.cfg) + timedelta(minutes=float(in_minutes))
        elif at:
            moment = datetime.strptime(at.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=now(self.cfg).tzinfo)
        else:
            raise ValueError("нужно указать, через сколько минут или во сколько")
        if moment.timestamp() <= time.time():
            raise ValueError("это время уже прошло")
        self.add(device, "reminder", moment.timestamp(), text)
        return f"Напоминание «{text}» поставлено на {self.when(moment.timestamp())}."

    def alarm(self, device: str, at: str, label: str = "", daily: bool = False) -> str:
        hours, minutes = (int(part) for part in at.strip().split(":")[:2])
        current = now(self.cfg)
        moment = current.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        if moment <= current:
            moment += timedelta(days=1)
        self.add(device, "alarm", moment.timestamp(), label, "daily" if daily else "")
        return f"Будильник на {moment:%H:%M}{' каждый день' if daily else ''} поставлен."

    def when(self, stamp: float) -> str:
        moment = datetime.fromtimestamp(stamp, now(self.cfg).tzinfo)
        today = now(self.cfg).date()
        day = "" if moment.date() == today else (" завтра" if moment.date() == today + timedelta(days=1) else f" {moment:%d.%m}")
        return f"{moment:%H:%M}{day}"

    def upcoming(self, device: str | None = None) -> list[Entry]:
        with self.lock:
            rows = self.db.execute("SELECT id, device, kind, fire_at, text, repeat FROM schedule ORDER BY fire_at").fetchall()
        return [Entry(*row) for row in rows if device is None or row[1] == device]

    def describe(self, entry: Entry) -> str:
        left = int(entry.fire_at - time.time())
        if entry.kind == "timer":
            return f"таймер {entry.text}: осталось {duration_words(max(left, 1))}"
        label = f" «{entry.text}»" if entry.text else ""
        return f"{KIND_WORDS[entry.kind]}{label} на {self.when(entry.fire_at)}{' каждый день' if entry.repeat else ''}"

    def schedule_text(self, device: str) -> str:
        entries = self.upcoming(device)
        return "; ".join(self.describe(entry) for entry in entries) if entries else "Ничего не запланировано."

    def cancel(self, device: str, what: str = "all") -> str:
        needle = what.strip().lower()
        entries = self.upcoming(device)
        chosen = [
            entry for entry in entries
            if needle in ("", "all", "все", "всё") or needle in entry.text.lower() or needle in KIND_WORDS[entry.kind] or needle in entry.kind
        ]
        with self.lock:
            for entry in chosen:
                self.db.execute("DELETE FROM schedule WHERE id = ?", (entry.id,))
            self.db.commit()
        return f"Отменил: {len(chosen)}." if chosen else "Такого не нашёл."

    def shopping(self, action: str, items: list[str] | None = None) -> str:
        items = [item.strip() for item in (items or []) if item and item.strip()]
        with self.lock:
            if action == "add":
                for item in items:
                    self.db.execute("INSERT OR IGNORE INTO shopping (item) VALUES (?)", (item,))
                self.db.commit()
                return f"Добавил в список покупок: {', '.join(items)}." if items else "Не сказано, что добавить."
            if action == "remove":
                removed = sum(self.db.execute("DELETE FROM shopping WHERE item LIKE ?", (f"%{item}%",)).rowcount for item in items)
                self.db.commit()
                return f"Убрал из списка: {removed}." if removed else "Такого в списке нет."
            if action == "clear":
                self.db.execute("DELETE FROM shopping")
                self.db.commit()
                return "Список покупок очищен."
            rows = self.db.execute("SELECT item FROM shopping ORDER BY id").fetchall()
        return "В списке покупок: " + ", ".join(row[0] for row in rows) + "." if rows else "Список покупок пуст."

    def today_text(self, device: str) -> str:
        end = now(self.cfg).replace(hour=23, minute=59, second=59).timestamp()
        today = [self.describe(entry) for entry in self.upcoming(device) if entry.kind != "timer" and entry.fire_at <= end]
        count = self.db.execute("SELECT COUNT(*) FROM shopping").fetchone()[0]
        parts = [f"Запланировано на сегодня: {'; '.join(today)}" if today else "На сегодня ничего не запланировано"]
        if count:
            parts.append(f"В списке покупок {count} {plural(count, ('позиция', 'позиции', 'позиций'))}")
        return ". ".join(parts) + "."


def specs(planner: Planner) -> list[dict]:
    from .music import current_device
    from .tools import weather
    from .tools.clock import describe

    def here() -> str:
        return current_device.get()

    def brief(args: dict) -> str:
        return f"{describe(now(planner.cfg))}. {weather.report(planner.cfg, None)} {planner.today_text(here())}"

    return [
        {
            "name": "set_timer",
            "description": "Поставить таймер: «поставь таймер на пять минут», «таймер на полчаса». Время переведи в секунды сам.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "integer", "description": "Сколько секунд до сигнала"},
                    "label": {"type": "string", "description": "Название таймера, если сказано (например, пицца)"},
                },
                "required": ["seconds"],
                "additionalProperties": False,
            },
            "run": lambda args: planner.timer(here(), int(args["seconds"]), args.get("label", "")),
        },
        {
            "name": "set_reminder",
            "description": "Поставить напоминание: «напомни через час позвонить маме», «напомни завтра в девять утра про врача». Укажи in_minutes ИЛИ at.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "О чём напомнить, коротко: «позвонить маме»"},
                    "in_minutes": {"type": "number", "description": "Через сколько минут"},
                    "at": {"type": "string", "description": "Когда, по местному времени, в формате ГГГГ-ММ-ДД ЧЧ:ММ. Дату считай от сегодняшней."},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            "run": lambda args: planner.reminder(here(), args["text"], args.get("in_minutes"), args.get("at")),
        },
        {
            "name": "set_alarm",
            "description": "Поставить будильник на время: «разбуди меня в семь тридцать», «будильник на шесть каждый день».",
            "parameters": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "description": "Время в формате ЧЧ:ММ, 24 часа"},
                    "label": {"type": "string", "description": "Подпись, если сказана"},
                    "daily": {"type": "boolean", "description": "Повторять каждый день"},
                },
                "required": ["time"],
                "additionalProperties": False,
            },
            "run": lambda args: planner.alarm(here(), args["time"], args.get("label", ""), bool(args.get("daily"))),
        },
        {
            "name": "show_schedule",
            "description": "Что запланировано: таймеры (сколько осталось), напоминания, будильники. Для «сколько осталось на таймере», «какие у меня будильники».",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "run": lambda args: planner.schedule_text(here()),
        },
        {
            "name": "cancel_schedule",
            "description": "Отменить таймер, напоминание или будильник. what: «все», «таймер», «будильник», «напоминание» или слово из названия.",
            "parameters": {
                "type": "object",
                "properties": {"what": {"type": "string", "description": "Что отменить"}},
                "additionalProperties": False,
            },
            "run": lambda args: planner.cancel(here(), args.get("what", "all")),
        },
        {
            "name": "shopping_list",
            "description": "Список покупок: add — добавить продукты, remove — убрать, show — прочитать список, clear — очистить.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "remove", "show", "clear"]},
                    "items": {"type": "array", "items": {"type": "string"}, "description": "Продукты в именительном падеже: молоко, хлеб"},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            "run": lambda args: planner.shopping(args["action"], args.get("items")),
        },
        {
            "name": "morning_brief",
            "description": "Утренняя сводка: дата, погода дома, что запланировано на сегодня и сколько позиций в списке покупок. Для «доброе утро», «что на сегодня», «сводка».",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "run": brief,
        },
    ]
