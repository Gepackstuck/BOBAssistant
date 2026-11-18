import json
import threading
from typing import Callable

from .config import ROOT

PATH = ROOT / "data" / "devices.json"
THEMES = ("dark", "light")
VOLUME_MIN = 10
VOLUME_MAX = 100
VOLUME_STEP = 10


class DeviceSettings:
    def __init__(self):
        self.lock = threading.Lock()
        self.listeners: list[Callable[[str], None]] = []
        self.data: dict[str, dict] = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}

    def get(self, device: str, key: str, default):
        return self.data.get(device, {}).get(key, default)

    def set(self, device: str, key: str, value) -> None:
        with self.lock:
            self.data.setdefault(device, {})[key] = value
            PATH.parent.mkdir(parents=True, exist_ok=True)
            PATH.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        for listener in self.listeners:
            listener(device)

    def enabled(self, device: str) -> bool:
        return self.get(device, "enabled", True)

    def voice(self, device: str) -> bool:
        return self.get(device, "voice", True)

    def set_voice(self, device: str, enabled: bool) -> None:
        self.set(device, "voice", enabled)

    def theme(self, device: str) -> str:
        value = self.get(device, "theme", "dark")
        return value if value in THEMES else "dark"

    def set_theme(self, device: str, theme: str) -> None:
        self.set(device, "theme", theme if theme in THEMES else "dark")

    def volume(self, device: str) -> int:
        return int(self.get(device, "volume", VOLUME_MAX))

    def set_volume(self, device: str, percent: int) -> int:
        level = min(VOLUME_MAX, max(VOLUME_MIN, round(percent / VOLUME_STEP) * VOLUME_STEP))
        self.set(device, "volume", level)
        return level

    def snapshot(self, device: str) -> dict:
        return {"type": "settings", "voice": self.voice(device), "theme": self.theme(device), "volume": self.volume(device)}

    def subscribe(self, listener: Callable[[str], None]) -> None:
        self.listeners.append(listener)
