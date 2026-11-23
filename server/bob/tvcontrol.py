import time
from typing import Callable

from .music import close, words
from .textnorm import plural

SHARE = 0.6
STEPS = 2
STEP_PERCENT = 5


class TvControl:
    def __init__(self, device: Callable):
        self.device = device

    def available(self) -> bool:
        target = self.device()
        return target is not None and getattr(target, "alive", False) and hasattr(target, "tv")

    def target(self):
        if not self.available():
            raise RuntimeError("телевизор не подключён")
        return self.device()

    def say_volume(self, state: dict) -> str:
        if state.get("muted"):
            return "Звук на телевизоре выключен."
        percent = int(state.get("percent", 0))
        return f"Громкость телевизора {percent} {plural(percent, ('процент', 'процента', 'процентов'))}."

    def volume(self, action: str, level: int | None = None, steps: int = STEPS) -> str:
        target = self.target()
        if action == "status":
            return self.say_volume(target.tv({"action": "state"}))
        if action == "set":
            if level is None:
                raise RuntimeError("не сказано, на сколько процентов")
            return self.say_volume(target.tv({"action": "volume_set", "percent": int(level)}))
        if action in ("up", "down"):
            percent = int(target.tv({"action": "state"}).get("percent", 0))
            delta = STEP_PERCENT * max(1, min(6, int(steps)))
            level = max(0, min(100, percent + (delta if action == "up" else -delta)))
            return self.say_volume(target.tv({"action": "volume_set", "percent": level}))
        if action in ("mute", "unmute"):
            state = target.tv({"action": action})
            return "Звук выключен." if action == "mute" else self.say_volume(state)
        raise RuntimeError("неизвестное действие с громкостью")

    def open_app(self, name: str) -> str:
        target = self.target()
        wanted = words(name)
        scored = []
        for app in target.apps:
            have = words(app["label"])
            share = sum(1 for word in wanted if any(close(word, other) for other in have)) / len(wanted) if wanted else 0.0
            scored.append((share, -len(have), app))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not scored or scored[0][0] < SHARE:
            raise RuntimeError(f"не нашёл приложение «{name}» на телевизоре")
        if len(scored) > 1 and scored[1][0] == scored[0][0] and scored[1][1] == scored[0][1]:
            options = ", ".join(item[2]["label"] for item in scored[:3])
            raise RuntimeError(f"не понял, какое приложение: {options}")
        app = scored[0][2]
        target.tv({"action": "launch", "package": app["package"]})
        return f"Открываю {app['label']}."

    def home(self) -> str:
        self.target().tv({"action": "home"})
        return "Главный экран."


def specs(control: TvControl) -> list[dict]:
    return [
        {
            "name": "tv_volume",
            "description": "Громкость телевизора: сделать громче или тише, поставить уровень в процентах, выключить или включить звук, узнать текущую. Не путай с громкостью музыки и голоса ассистента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["up", "down", "set", "mute", "unmute", "status"]},
                    "level": {"type": "integer", "description": "Уровень в процентах для action=set"},
                    "steps": {"type": "integer", "description": "Сколько шагов по 5 процентов (по умолчанию 2, «намного громче» 4)"},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
            "run": lambda args: control.volume(args["action"], args.get("level"), args.get("steps", STEPS)),
        },
        {
            "name": "tv_open_app",
            "description": "Открыть приложение на телевизоре по названию: «открой ютуб», «запусти кинопоиск», «включи твич». Не для музыки Яндекса.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "Название приложения как сказал пользователь"}}, "required": ["name"], "additionalProperties": False},
            "run": lambda args: control.open_app(args["name"]),
        },
        {
            "name": "tv_home",
            "description": "Вернуться на главный экран телевизора: «домой», «главный экран».",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "run": lambda args: control.home(),
        },
    ]
