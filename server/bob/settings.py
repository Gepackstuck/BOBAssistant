import json
import threading
from typing import Callable

from .config import ROOT

PATH = ROOT / "data" / "devices.json"


class DeviceSettings:
    def __init__(self):
        self.lock = threading.Lock()
        self.listeners: list[Callable[[str, bool], None]] = []
        self.data: dict[str, dict] = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}

    def voice(self, device: str) -> bool:
        return self.data.get(device, {}).get("voice", True)

    def set_voice(self, device: str, enabled: bool) -> None:
        with self.lock:
            self.data.setdefault(device, {})["voice"] = enabled
            PATH.parent.mkdir(parents=True, exist_ok=True)
            PATH.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        for listener in self.listeners:
            listener(device, enabled)

    def subscribe(self, listener: Callable[[str, bool], None]) -> None:
        self.listeners.append(listener)
