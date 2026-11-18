import re
import time

from .llm import make_llm
from .tools import build_registry
from .tools.clock import describe, now

SYSTEM = """Ты {name}, домашний голосовой ассистент. Твои ответы произносятся вслух.
Правила:
- Отвечай по-русски, коротко: одно-два предложения, главное сначала.
- Без списков, разметки, эмодзи и ссылок.
- Числа, время и единицы пиши словами в правильном падеже: «минус один градус», «от нуля до пяти градусов», «в половине восьмого».
- На вопрос о погоде сначала обязательно вызови инструмент weather, о времени и дате — current_time, на любой расчёт — calculator. Называть такие данные без вызова инструмента запрещено: ты их не знаешь.
- Если подходящего инструмента нет или он не ответил, честно скажи, что не знаешь. Ничего не выдумывай.
- Не задавай встречных вопросов и не спрашивай «а у вас как?». Уточняй только если просьбу правда нельзя понять.
Сегодня {today}."""

TIME_RE = re.compile(r"котор\w* (сейчас )?час|сколько (сейчас )?времен", re.IGNORECASE)
CANCEL_RE = re.compile(r"^(стоп|отмена|ничего|не надо|забудь|отбой)\b", re.IGNORECASE)


class Assistant:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.registry = build_registry(cfg)
        self.llm = make_llm(cfg["llm"])
        self.session_seconds = cfg["llm"]["session_minutes"] * 60
        self.session: list = self.llm.new_session()
        self.last_turn = 0.0

    def system_prompt(self) -> str:
        today = describe(now(self.cfg)).split(", ", 1)[1]
        return SYSTEM.format(name=self.cfg["persona"]["name"], today=today)

    def fast_path(self, text: str) -> str | None:
        if CANCEL_RE.search(text.strip()):
            return ""
        if TIME_RE.search(text):
            return f"Сейчас {now(self.cfg):%H:%M}."
        return None

    def handle(self, text: str) -> str:
        quick = self.fast_path(text)
        if quick is not None:
            return quick
        if time.monotonic() - self.last_turn > self.session_seconds:
            self.session = self.llm.new_session()
        answer = self.llm.reply(self.session, self.system_prompt(), text, self.registry)
        self.last_turn = time.monotonic()
        return answer or "Не получилось ответить."
