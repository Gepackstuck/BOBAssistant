import re
import time

from num2words import num2words

from .capabilities import HELP_RE, help_text
from .llm import make_llm
from .memory import Memory
from .home import Home
from .music import Music, current_device
from .planner import Planner
from .tvcontrol import TvControl
from .settings import VOLUME_MAX, VOLUME_MIN, VOLUME_STEP, DeviceSettings
from .tools import build_registry
from .tools.clock import describe, now

SYSTEM = """Ты {name}, домашний голосовой ассистент. Твои ответы произносятся вслух.
Правила:
- Отвечай по-русски. Вслух произносится только короткая часть: одно-два предложения, главное сначала. Если по теме есть что добавить (подробности, цифры, перечисление), допиши после разделителя ||| одно-два коротких предложения: они появятся только на плашке и не будут произнесены. Часть до разделителя должна быть полным ответом на вопрос сама по себе (на «сколько будет 23 на 17» это «триста девяносто один»). В подробности пиши только то, что есть в ответе инструмента, ничего не добавляй от себя. Разделитель ставь только когда подробности правда есть и они полезны, на простые вопросы («который час», «как дела», расчёты, шутки), на включение и управление музыкой, таймеры и напоминания его не ставь.
- Без списков, разметки, эмодзи и ссылок.
- Числа, время и единицы пиши словами в правильном падеже: «минус один градус», «от нуля до пяти градусов», «через двадцать минут».
- На вопрос о погоде сначала обязательно вызови инструмент weather, о времени и дате — current_time, на любой расчёт — calculator. Называть такие данные без вызова инструмента запрещено: ты их не знаешь.
- За свежими фактами (новости, курсы, счёт матча, цены) обращайся к web_search и пересказывай коротко, без ссылок. У новостей в начале стоит дата: сверяй её с сегодняшней. Если за нужный день данных нет, так и скажи («свежих данных не нашёл», можно назвать, на какую дату есть).
- На любой вопрос о фактах про человека, группу, место, фильм, песню или понятие («кто такой», «сколько лет», «когда родился», «что такое») сначала вызови encyclopedia и отвечай по её тексту, а не по памяти. На «кто такой» отвечай, кем человек является и чем известен, без возраста и дат. Возраст называй только если о нём спросили, бери число из пометки «Полных лет на сегодня», сам не считай. В ответе называй, о ком речь («Лолита Милявская, ей шестьдесят три года»). Фразу «не нашёл» можно говорить только после вызова инструмента.
- Таймеры, напоминания, будильники и список покупок ставь только инструментами set_timer, set_reminder, set_alarm, shopping_list (время переводи в секунды, минуты или ЧЧ:ММ сам), потом коротко подтверди. На «доброе утро» и «что на сегодня» вызови morning_brief и перескажи его.
- Про умный дом (свет, лампы, розетки, шторы, сценарии, датчики, температура) ты ничего не знаешь без инструмента: на любой вопрос о состоянии («какой свет включён», «включена ли лампа», «какая температура») сначала вызови home_status, на просьбу включить, выключить или изменить вызови home_control или home_scene. Отвечай только по тому, что вернул инструмент: называй устройства именно их названиями из ответа, ничего не домысливай (комнаты, цвета, яркость). Для температуры и влажности передавай в name слово «температура» или «влажность»; если датчика нет, так и скажи. Не говори, что сделал, пока инструмент не вернул успех; при ошибке так и скажи.
- Громкостью телевизора, звуком, приложениями на телевизоре и возвратом на главный экран управляй инструментами tv_volume, tv_open_app, tv_home; громкость музыки и голоса ассистента не путай с громкостью телевизора.
- Когда просят запомнить или рассказывают о себе важное, вызови remember. Когда просят забыть — forget.
- Если подходящего инструмента нет или он не ответил, честно скажи, что не знаешь. Ничего не выдумывай.
- Если инструмент вернул ошибку или ничего не нашёл (особенно в музыке), не рассказывай, кто или что это, и не угадывай: скажи, что не расслышал, и попроси повторить название.
- Никогда не заканчивай ответ вопросом, предложением помощи или прощанием («чем ещё помочь», «нужно что-то ещё», «обращайтесь»). Отвечай по сути и замолкай. Уточняй только если просьбу правда нельзя понять.
- Если просят подробнее, ответь развёрнуто, до шести предложений, и произнеси всё вслух (разделитель ||| не нужен). Если просят короче, ответь одной короткой фразой без разделителя.
Сегодня {today}."""

TIME_RE = re.compile(r"котор\w* (сейчас )?час|сколько (сейчас )?врем|что (сейчас )?по времени|какое (сейчас )?время", re.IGNORECASE)
FILLER_TAIL_RE = re.compile(
    r"[\s,.!—-]*(?:а у вас как дела|как у вас дела|как ваши дела|чем (?:ещё |еще )?могу (?:вам )?помочь|что (?:вас )?(?:ещё |еще )?вас интересует|что вас (?:ещё |еще )?интересует|"
    r"могу ли я (?:ещё |еще )?чем-то помочь|нужна ли (?:вам )?(?:ещё |еще )?помощь|нужно ли (?:вам )?(?:ещё |еще )?что-нибудь|хотите (?:ещё |еще )?что-нибудь|"
    r"хотите узнать (?:ещё |еще )?больше|есть ли (?:ещё |еще )?вопросы|если (?:что|понадобится|нужно)[^.!?]*|обращайтесь[^.!?]*|я к вашим услугам|"
    r"всегда (?:рад|готов)[^.!?]*|больше не буду беспокоить[^.!?]*)\s*[?!.]*\s*$",
    re.IGNORECASE,
)
REMEMBER_RE = re.compile(r"^\s*запомни(?:те)?[\s,:-]+(?:что\s+)?(.+)$", re.IGNORECASE | re.DOTALL)
FORGET_RE = re.compile(r"^\s*забудь(?:те)?[\s,:-]+(?:про\s+|что\s+|о\s+)?(.+)$", re.IGNORECASE | re.DOTALL)
VOICE_OFF_RE = re.compile(r"(?:выключи|отключи|убери)\s+голос|отвечай\s+(?:только\s+)?(?:текстом|письменно|без\s+голоса)|не\s+отвечай\s+голосом|без\s+голоса", re.IGNORECASE)
VOICE_ON_RE = re.compile(r"(?:включи|верни)\s+голос|отвечай\s+голосом|говори\s+голосом", re.IGNORECASE)
THEME_WORD = r"(?:тем\w+|плашк\w+|оформлени\w+|стил\w+)"
THEME_LIGHT_RE = re.compile(rf"светл\w+\s+{THEME_WORD}|{THEME_WORD}\s+светл\w+", re.IGNORECASE)
THEME_DARK_RE = re.compile(rf"[тТ][ёе]мн\w+\s+{THEME_WORD}|{THEME_WORD}\s+[тТ][ёе]мн\w+", re.IGNORECASE)
THEME_TOGGLE_RE = re.compile(rf"(?:смени|поменяй|переключи)\s+{THEME_WORD}", re.IGNORECASE)
VOICE_LOUDER_RE = re.compile(r"(?:говори|отвечай)\s+громче|голос\s+громче|громче\s+(?:говори|отвечай)", re.IGNORECASE)
VOICE_QUIETER_RE = re.compile(r"(?:говори|отвечай)\s+тише|голос\s+тише|тише\s+(?:говори|отвечай)", re.IGNORECASE)
VOICE_LEVEL_RE = re.compile(r"громкость\s+(?:голоса|ассистента|боба|джарвиса|ответов)\s+(?:на\s+)?(\S+?)(?:\s*(?:%|процент\w*))?\s*$", re.IGNORECASE)
LEVEL_WORDS = {
    "десять": 10, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90, "сто": 100,
}
STYLE_CORNER_RE = re.compile(r"(?:включи|поставь|сделай|переключи|верни|режим|оформление|вариант)[^.!?]*\b(?:угловое|угловой|угловую|уголок|угол|в\s+углу)\b|\b(?:угловое|угловой|уголок)\s+(?:оформление|режим|вариант)", re.IGNORECASE)
STYLE_PLATE_RE = re.compile(r"(?:верни|включи|поставь|сделай)\s+(?:обычн\w+\s+|стандартн\w+\s+|прежн\w+\s+|старую\s+)?плашк\w+\s*$|плашка\s+как\s+раньше", re.IGNORECASE)
TV_LOUDER_RE = re.compile(r"^\s*(?:сделай\s+)?(?:по)?громче\b|^\s*добавь\s+(?:громкость|звук)", re.IGNORECASE)
TV_QUIETER_RE = re.compile(r"^\s*(?:сделай\s+)?(?:по)?тише\b|^\s*убавь\s+(?:громкость|звук)", re.IGNORECASE)
TV_MUTE_RE = re.compile(r"^\s*(?:выключи|убери|отключи)\s+звук\b|^\s*без\s+звука\b|^\s*заглуши\b", re.IGNORECASE)
TV_UNMUTE_RE = re.compile(r"^\s*(?:включи|верни)\s+звук\b", re.IGNORECASE)
LIGHT_STATE_RE = re.compile(r"какой\s+(?:сейчас\s+)?свет\s+(?:сейчас\s+)?(?:включ[её]н|горит)|что\s+(?:сейчас\s+)?(?:включено|горит)|(?:включ[её]н|горит)\s+ли\s+(?:весь\s+|какой-нибудь\s+)?свет|какие\s+лампы\s+(?:включены|горят)", re.IGNORECASE)
EQUALIZER_ON_RE = re.compile(r"(?:включи|верни|сделай|поставь)\s+(?:разноцветн\w+|цветн\w+|красив\w+)\s+(?:эквалайзер|полоск\w+)|(?:эквалайзер|полоск\w+)\s+(?:разноцветн\w+|цветн\w+)", re.IGNORECASE)
EQUALIZER_OFF_RE = re.compile(r"(?:верни|включи|сделай|поставь)\s+(?:обычн\w+|стандартн\w+|прежн\w+|классическ\w+)\s+(?:эквалайзер|полоск\w+)|(?:обычн\w+|классическ\w+)\s+(?:эквалайзер|полоск\w+)", re.IGNORECASE)
CLOSING_CORE = {
    "спасибо", "благодарю", "хватит", "достаточно", "довольно", "отбой", "отмена", "стоп", "ничего", "надо",
    "ладно", "понятно", "ясно", "всё", "все", "пока", "свидания", "свободен", "отключись", "замолчи", "помолчи", "забудь",
}
CLOSING_FILLER = {
    "нет", "не", "большое", "это", "на", "этом", "до", "ну", "да", "ага", "угу", "хорошо", "окей", "ок", "всего", "доброго",
    "спокойной", "ночи", "боб", "джарвис", "миньон", "подручный", "сбер", "тебе", "вам", "очень",
}
DETAIL_MARK = "|||"
MORE_RE = re.compile(r"^\s*(?:расскажи\s+)?(?:по)?подробнее|развёрнуто|более\s+подробно", re.IGNORECASE)
PLAN_RE = re.compile(r"таймер|напомни|напоминани|будильн|разбуди|список покупок|списке покупок|в список|из списка|убери|осталось", re.IGNORECASE)
MORNING_RE = re.compile(r"доброе\s+утро|что\s+(?:у\s+меня\s+)?на\s+сегодня|утренн\w+\s+сводк|сводк\w+\s+на\s+(?:сегодня|день)", re.IGNORECASE)
SHORTER_RE = re.compile(r"^\s*(?:скажи\s+)?короче|кратко|одним\s+предложением", re.IGNORECASE)
WORD_RE = re.compile(r"[а-яёa-z]+", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


class Assistant:
    def __init__(self, cfg: dict, settings: DeviceSettings):
        self.cfg = cfg
        self.settings = settings
        self.memory = Memory()
        self.music = Music(cfg)
        self.planner = Planner(cfg)
        self.home = Home()
        self.tv = TvControl(lambda: self.music.devices.get("tv"))
        self.registry = build_registry(cfg, self.memory, self.music, self.planner, self.home, self.tv)
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

    def voice_volume_reply(self, percent: int) -> str:
        return f"Громкость голоса {num2words(percent, lang='ru')} процентов."

    def fast_path(self, text: str, device: str) -> str | None:
        played = self.music.fast(text, device)
        if played is not None:
            return played
        if device.startswith("tv") and self.tv.available():
            for pattern, action in ((TV_LOUDER_RE, "up"), (TV_QUIETER_RE, "down"), (TV_MUTE_RE, "mute"), (TV_UNMUTE_RE, "unmute")):
                if pattern.search(text):
                    return self.tv.volume(action)
        if THEME_LIGHT_RE.search(text):
            self.settings.set_theme(device, "light")
            return "Хорошо, светлая плашка."
        if THEME_DARK_RE.search(text):
            self.settings.set_theme(device, "dark")
            return "Хорошо, тёмная плашка."
        if THEME_TOGGLE_RE.search(text):
            light = self.settings.theme(device) == "dark"
            self.settings.set_theme(device, "light" if light else "dark")
            return "Хорошо, светлая плашка." if light else "Хорошо, тёмная плашка."
        if self.home.connected() and LIGHT_STATE_RE.search(text):
            return self.home.overview()
        asked = HELP_RE.match(text)
        if asked:
            return help_text(self, device, asked.group("rest"))
        level = VOICE_LEVEL_RE.search(text)
        if level:
            token = level.group(1).strip(" .%").lower()
            percent = int(token) if token.isdigit() else LEVEL_WORDS.get(token)
            if percent is not None:
                return self.voice_volume_reply(self.settings.set_volume(device, percent))
        if VOICE_LOUDER_RE.search(text):
            current = self.settings.volume(device)
            if current >= VOLUME_MAX:
                return "Это уже максимум, дальше только в настройках звука."
            return self.voice_volume_reply(self.settings.set_volume(device, current + VOLUME_STEP))
        if VOICE_QUIETER_RE.search(text):
            current = self.settings.volume(device)
            if current <= VOLUME_MIN:
                return "Тише уже некуда."
            return self.voice_volume_reply(self.settings.set_volume(device, current - VOLUME_STEP))
        if STYLE_CORNER_RE.search(text):
            if not device.startswith("tv"):
                return "Угловое оформление есть только на телевизоре, здесь доступна плашка."
            self.settings.set_style(device, "corner")
            return "Хорошо, теперь всё в левом нижнем углу."
        if STYLE_PLATE_RE.search(text):
            if not device.startswith("tv"):
                return "Здесь и так плашка."
            self.settings.set_style(device, "plate")
            return "Хорошо, снова плашка."
        if EQUALIZER_ON_RE.search(text):
            self.settings.set_indicator(device, "colorful")
            return "Хорошо, теперь эквалайзер разноцветный."
        if EQUALIZER_OFF_RE.search(text):
            self.settings.set_indicator(device, "classic")
            return "Хорошо, эквалайзер снова обычный."
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
        if self.is_end(text):
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
        spoken, _, extra = answer.partition(DETAIL_MARK)
        spoken = self.tidy(spoken) or "Не получилось ответить."
        extra = extra.replace(DETAIL_MARK, " ").strip()
        if MORE_RE.search(text) or MORNING_RE.search(text):
            spoken, extra = f"{spoken} {extra}".strip(), ""
        elif SHORTER_RE.search(text) or PLAN_RE.search(text):
            extra = ""
        return f"{spoken}{DETAIL_MARK}{extra}" if extra else spoken

    def is_end(self, text: str) -> bool:
        first = SENTENCE_SPLIT_RE.split(text.strip())[0]
        words = [word.lower() for word in WORD_RE.findall(first)]
        return bool(words) and len(words) <= 8 and all(word in CLOSING_CORE or word in CLOSING_FILLER for word in words) and any(word in CLOSING_CORE for word in words)

    def tidy(self, answer: str) -> str:
        trimmed = FILLER_TAIL_RE.sub("", answer).strip() or answer
        sentences = SENTENCE_SPLIT_RE.split(trimmed)
        if len(sentences) > 1 and sentences[-1].rstrip().endswith("?"):
            trimmed = " ".join(sentences[:-1]).strip()
        return trimmed
