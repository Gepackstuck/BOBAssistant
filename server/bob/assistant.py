import re
import time

from .llm import make_llm
from .memory import Memory
from .music import Music, current_device
from .settings import DeviceSettings
from .tools import build_registry
from .tools.clock import describe, now

SYSTEM = """Ты {name}, домашний голосовой ассистент. Твои ответы произносятся вслух.
Правила:
- Отвечай по-русски, коротко: одно-два предложения, главное сначала.
- Без списков, разметки, эмодзи и ссылок.
- Числа, время и единицы пиши словами в правильном падеже: «минус один градус», «от нуля до пяти градусов», «через двадцать минут».
- На вопрос о погоде сначала обязательно вызови инструмент weather, о времени и дате — current_time, на любой расчёт — calculator. Называть такие данные без вызова инструмента запрещено: ты их не знаешь.
- За свежими фактами (новости, курсы, счёт матча, цены) обращайся к web_search и пересказывай коротко, без ссылок. У новостей в начале стоит дата: сверяй её с сегодняшней. Если за нужный день данных нет, так и скажи («свежих данных не нашёл», можно назвать, на какую дату есть).
- Когда просят запомнить или рассказывают о себе важное, вызови remember. Когда просят забыть — forget.
- Если подходящего инструмента нет или он не ответил, честно скажи, что не знаешь. Ничего не выдумывай.
- Не задавай встречных вопросов и не спрашивай «а у вас как?». Уточняй только если просьбу правда нельзя понять.
Сегодня {today}."""

TIME_RE = re.compile(r"котор\w* (сейчас )?час|сколько (сейчас )?врем|что (сейчас )?по времени|какое (сейчас )?время", re.IGNORECASE)
FILLER_TAIL_RE = re.compile(
    r"[\s,.!—-]*(?:а у вас как дела|как у вас дела|как ваши дела|чем (?:ещё |еще )?могу (?:вам )?помочь|что (?:вас )?(?:ещё |еще )?вас интересует|что вас (?:ещё |еще )?интересует|могу ли я (?:ещё |еще )?чем-то помочь|нужна ли (?:вам )?(?:ещё |еще )?помощь)\s*\?*\s*$",
    re.IGNORECASE,
)
REMEMBER_RE = re.compile(r"^\s*запомни(?:те)?[\s,:-]+(?:что\s+)?(.+)$", re.IGNORECASE | re.DOTALL)
FORGET_RE = re.compile(r"^\s*забудь(?:те)?[\s,:-]+(?:про\s+|что\s+|о\s+)?(.+)$", re.IGNORECASE | re.DOTALL)
VOICE_OFF_RE = re.compile(r"(?:выключи|отключи|убери)\s+голос|отвечай\s+(?:только\s+)?(?:текстом|письменно|без\s+голоса)|не\s+отвечай\s+голосом|без\s+голоса", re.IGNORECASE)
VOICE_ON_RE = re.compile(r"(?:включи|верни)\s+голос|отвечай\s+голосом|говори\s+голосом", re.IGNORECASE)
CANCEL_RE = re.compile(r"^(стоп|отмена|ничего|не надо|забудь|отбой)\b", re.IGNORECASE)


class Assistant:
    def __init__(self, cfg: dict, settings: DeviceSettings):
        self.cfg = cfg
        self.settings = settings
        self.memory = Memory()
        self.music = Music(cfg)
        self.registry = build_registry(cfg, self.memory, self.music)
        self.llm = make_llm(cfg["llm"])
        self.session_seconds = cfg["llm"]["session_minutes"] * 60
        self.session: list = self.llm.new_session()
        self.last_turn = 0.0

    def system_prompt(self) -> str:
        today = describe(now(self.cfg)).split(", ", 1)[1]
        prompt = SYSTEM.format(name=self.cfg["persona"]["name"], today=today)
        facts = self.memory.facts()
        if facts:
            prompt += "\nЧто ты знаешь о пользователе и семье:\n" + "\n".join(f"- {fact}" for fact in facts)
        return prompt

    def fast_path(self, text: str, device: str) -> str | None:
        played = self.music.fast(text, device)
        if played is not None:
            return played
        if VOICE_OFF_RE.search(text):
            self.settings.set_voice(device, False)
            return "Хорошо, теперь отвечаю только текстом."
        if VOICE_ON_RE.search(text):
            self.settings.set_voice(device, True)
            return "Снова отвечаю голосом."
        remembered = REMEMBER_RE.match(text)
        if remembered:
            fact = remembered.group(1).strip(" .!?")
            self.memory.remember(fact[:1].upper() + fact[1:])
            return "Запомнил."
        forgotten = FORGET_RE.match(text)
        if forgotten:
            removed = self.memory.forget(forgotten.group(1).strip(" .!?"))
            return "Забыл." if not removed.endswith(": 0") else "Такого не помню."
        if CANCEL_RE.search(text.strip()):
            return ""
        if TIME_RE.search(text):
            return f"Сейчас {now(self.cfg):%H:%M}."
        return None

    def handle(self, text: str, device: str = "mac") -> str:
        quick = self.fast_path(text, device)
        if quick is not None:
            return quick
        current_device.set(device)
        if time.monotonic() - self.last_turn > self.session_seconds:
            self.session = self.llm.new_session()
        answer = self.llm.reply(self.session, self.system_prompt(), text, self.registry)
        self.last_turn = time.monotonic()
        trimmed = FILLER_TAIL_RE.sub("", answer).strip()
        return trimmed or answer or "Не получилось ответить."
