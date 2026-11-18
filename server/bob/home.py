import json
import threading
import time

import httpx

from .config import ROOT
from .music import close, current_device, words

CONFIG_PATH = ROOT / "secrets" / "home_assistant.json"
CACHE_SECONDS = 60
SHARE = 0.6
CONTROL_DOMAINS = ("light", "switch", "fan", "cover", "climate", "input_boolean", "lock")
READ_DOMAINS = ("sensor", "binary_sensor", "climate", "light", "switch", "cover", "fan", "lock")
COLORS = {
    "красн": "red", "син": "blue", "голуб": "lightblue", "зелен": "green", "зелён": "green", "желт": "yellow", "жёлт": "yellow",
    "оранжев": "orange", "фиолетов": "purple", "лилов": "violet", "розов": "pink", "бел": "white", "бирюзов": "turquoise",
}
NUMBERS = {
    "один": "1", "одна": "1", "одно": "1", "первая": "1", "первый": "1", "первое": "1", "первую": "1",
    "два": "2", "две": "2", "вторая": "2", "второй": "2", "второе": "2", "вторую": "2",
    "три": "3", "третья": "3", "третий": "3", "третье": "3", "третью": "3",
    "четыре": "4", "четвертая": "4", "четвертый": "4", "четвёртая": "4", "четвёртый": "4",
    "пять": "5", "пятая": "5", "пятый": "5", "шесть": "6", "шестая": "6", "шестой": "6",
}
WARM = ("тепл",)
COLD = ("холодн", "дневн")


def tokens(text: str) -> list[str]:
    return [NUMBERS.get(word, word) for word in words(text)]


class Home:
    def __init__(self):
        self.lock = threading.Lock()
        self.cache: tuple[float, list[dict]] = (0.0, [])
        self.notify = None

    def settings(self) -> dict | None:
        if not CONFIG_PATH.exists():
            return None
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if data.get("url") and data.get("token") else None

    def connected(self) -> bool:
        return self.settings() is not None

    def call(self, method: str, path: str, body: dict | None = None):
        config = self.settings()
        if config is None:
            raise RuntimeError("Home Assistant не подключён")
        response = httpx.request(
            method, config["url"].rstrip("/") + path, json=body, timeout=10,
            headers={"Authorization": f"Bearer {config['token']}"},
        )
        response.raise_for_status()
        return response.json() if response.content else None

    def entities(self) -> list[dict]:
        with self.lock:
            if time.time() - self.cache[0] > CACHE_SECONDS:
                self.cache = (time.time(), self.call("GET", "/api/states"))
            return self.cache[1]

    def refresh(self) -> None:
        with self.lock:
            self.cache = (0.0, [])

    def find(self, name: str, domains: tuple[str, ...]) -> dict:
        wanted = tokens(name)
        scored = []
        for entity in self.entities():
            if entity["entity_id"].split(".")[0] not in domains:
                continue
            title = tokens(entity.get("attributes", {}).get("friendly_name", entity["entity_id"]))
            share = sum(1 for word in wanted if any(close(word, other) for other in title)) / len(wanted) if wanted else 0.0
            scored.append((share, -len(title), entity))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not scored or scored[0][0] < SHARE:
            raise RuntimeError(f"не нашёл устройство «{name}»")
        if len(scored) > 1 and scored[1][0] == scored[0][0] and scored[1][1] == scored[0][1]:
            names = ", ".join(entity.get("attributes", {}).get("friendly_name", entity["entity_id"]) for _, _, entity in scored[:3])
            raise RuntimeError(f"не понял, какое именно: {names}. Попроси уточнить")
        return scored[0][2]

    def service(self, domain: str, service: str, data: dict) -> None:
        self.call("POST", f"/api/services/{domain}/{service}", data)
        self.refresh()

    def lamp_payload(self, entity_id: str) -> dict:
        entity = self.call("GET", f"/api/states/{entity_id}")
        attributes = entity.get("attributes", {})
        on = entity["state"] == "on"
        brightness = attributes.get("brightness")
        return {
            "type": "lamp", "name": attributes.get("friendly_name", entity_id), "on": on,
            "rgb": list(attributes.get("rgb_color") or [255, 205, 130]),
            "brightness": round(brightness * 100 / 255) if brightness is not None else (100 if on else 0),
        }

    def announce_lamp(self, entity_id: str) -> None:
        if self.notify is None or not entity_id.startswith("light."):
            return
        try:
            self.notify(current_device.get(), self.lamp_payload(entity_id))
        except Exception as error:
            print(f"[дом] {error}", flush=True)

    def control(self, name: str, action: str, brightness: int | None = None, color: str | None = None) -> str:
        entity = self.find(name, CONTROL_DOMAINS)
        entity_id = entity["entity_id"]
        domain = entity_id.split(".")[0]
        title = entity.get("attributes", {}).get("friendly_name", entity_id)
        data: dict = {"entity_id": entity_id}
        if action == "off":
            self.service(domain, {"cover": "close_cover", "lock": "lock"}.get(domain, "turn_off"), data)
            self.announce_lamp(entity_id)
            return f"{title}: выключено."
        if action == "toggle":
            self.service(domain, "toggle", data)
            self.announce_lamp(entity_id)
            return f"{title}: переключено."
        if domain == "light":
            if brightness is not None:
                data["brightness_pct"] = max(1, min(100, int(brightness)))
            if color:
                lowered = color.lower().replace("ё", "е")
                warm = any(lowered.startswith(prefix) for prefix in WARM)
                cold = any(lowered.startswith(prefix) for prefix in COLD)
                if warm:
                    data["color_temp_kelvin"] = 2700
                elif cold:
                    data["color_temp_kelvin"] = 5500
                else:
                    name_en = next((value for key, value in COLORS.items() if lowered.startswith(key.replace("ё", "е"))), None)
                    if name_en is None:
                        raise RuntimeError(f"не знаю цвет «{color}»")
                    data["color_name"] = name_en
        self.service(domain, {"cover": "open_cover", "lock": "unlock"}.get(domain, "turn_on"), data)
        self.announce_lamp(entity_id)
        details = f", яркость {data['brightness_pct']} процентов" if "brightness_pct" in data else ""
        return f"{title}: включено{', ' + color if color else ''}{details}."

    def scene(self, name: str) -> str:
        wanted = tokens(name)
        for entity in self.entities():
            domain = entity["entity_id"].split(".")[0]
            if domain not in ("scene", "script"):
                continue
            title = entity.get("attributes", {}).get("friendly_name", entity["entity_id"])
            have = tokens(title)
            if wanted and sum(1 for word in wanted if any(close(word, other) for other in have)) / len(wanted) >= SHARE:
                self.service(domain, "turn_on", {"entity_id": entity["entity_id"]})
                return f"Запустил «{title}»."
        raise RuntimeError(f"не нашёл сценарий «{name}»")

    def status(self, name: str) -> str:
        entity = self.find(name, READ_DOMAINS)
        attributes = entity.get("attributes", {})
        title = attributes.get("friendly_name", entity["entity_id"])
        unit = attributes.get("unit_of_measurement", "")
        state = {"on": "включено", "off": "выключено", "unavailable": "недоступно"}.get(entity["state"], entity["state"])
        return f"{title}: {state}{' ' + unit if unit and entity['state'] not in ('on', 'off', 'unavailable') else ''}."

    def overview(self) -> str:
        lights = [entity for entity in self.entities() if entity["entity_id"].startswith("light.")]
        on = [entity.get("attributes", {}).get("friendly_name", entity["entity_id"]) for entity in lights if entity["state"] == "on"]
        return f"Свет включён: {', '.join(on)}." if on else "Весь свет выключен."


def specs(home: Home) -> list[dict]:
    return [
        {
            "name": "home_control",
            "description": "Управлять устройством умного дома: включить или выключить лампу, свет, розетку, вентилятор, шторы, замок; яркость и цвет лампы. Название бери как сказал пользователь («лампа в спальне»).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Название устройства"},
                    "action": {"type": "string", "enum": ["on", "off", "toggle"]},
                    "brightness": {"type": "integer", "description": "Яркость в процентах, если сказана"},
                    "color": {"type": "string", "description": "Цвет по-русски (красный, синий, тёплый, холодный), если сказан"},
                },
                "required": ["name", "action"],
                "additionalProperties": False,
            },
            "run": lambda args: home.control(args["name"], args["action"], args.get("brightness"), args.get("color")),
        },
        {
            "name": "home_scene",
            "description": "Запустить сценарий умного дома: «включи сценарий вечер», «я ухожу».",
            "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "Название сценария"}}, "required": ["name"], "additionalProperties": False},
            "run": lambda args: home.scene(args["name"]),
        },
        {
            "name": "home_status",
            "description": "Узнать состояние устройства или показание датчика: температура, влажность, включён ли свет, закрыта ли дверь. Без названия: какой свет включён.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "Название устройства или датчика"}}, "additionalProperties": False},
            "run": lambda args: home.status(args["name"]) if args.get("name") else home.overview(),
        },
    ]
