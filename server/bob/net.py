import json
import os
import secrets
import threading
import time

from websockets.sync.server import serve

from .config import ROOT
from .devices import Device, Displays, RemoteDevice, plate_payload
from .pipeline import Brain, Listener, scaled

TOKEN_FILE = ROOT / "secrets" / "token"
DEMO_REQUEST = "какая погода завтра в Москве"
DEMO_ANSWER = "Завтра в Москве от нуля до пяти градусов, мокрый снег."


def device_token(cfg: dict) -> str:
    from_env = os.environ.get(cfg["network"]["token_env"] or "")
    if from_env:
        return from_env
    if not TOKEN_FILE.exists():
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(secrets.token_urlsafe(24))
        TOKEN_FILE.chmod(0o600)
    return TOKEN_FILE.read_text().strip()


class DeviceServer(threading.Thread):
    def __init__(self, cfg: dict, brain: Brain, displays: Displays):
        super().__init__(daemon=True, name="device-server")
        self.cfg = cfg
        self.brain = brain
        self.displays = displays
        self.token = device_token(cfg)
        self.devices: dict[str, Device] = {}
        self.music = brain.assistant.music
        self.music.bind(self.devices)
        brain.settings.subscribe(self.push_settings)

    def push_settings(self, name: str) -> None:
        self.displays.publish(name, self.brain.settings.snapshot(name))

    def sender(self, name: str):
        device = self.devices.get(name)
        if device is not None:
            return device.plate
        return lambda phase, request="", answer="", voice=True, theme="dark", window=0: self.displays.publish(
            name, plate_payload(phase, request, answer, voice, theme, window)
        )

    def fire(self, entry) -> None:
        name = entry.device if self.devices.get(entry.device) and self.devices[entry.device].alive else "mac"
        device = self.devices.get(name)
        if device is None:
            return
        text = {
            "timer": f"Таймер {entry.text} завершён.",
            "reminder": f"Напоминаю: {entry.text}.",
        }.get(entry.kind, f"Будильник. {entry.text or 'Пора вставать.'}")
        settings = self.brain.settings
        voice = settings.voice(name)
        device.plate("answer", "", text, voice, settings.theme(name))
        if voice:
            tts = self.brain.tts
            for _ in range(3 if entry.kind == "alarm" else 2):
                device.chime()
                device.play(scaled(tts.stream(text, tts.voices[tts.default_voice]), settings.volume(name)), tts.sample_rate)
                time.sleep(4)
        else:
            time.sleep(20)
        device.plate("idle")

    def announce(self, name: str, text: str, voice: str | None) -> str:
        device = self.devices.get(name)
        if device is None or not device.alive:
            return f"устройство {name} не подключено"
        tts = self.brain.tts
        profile = tts.voices.get(voice or "", tts.voices[tts.default_voice])
        device.plate("answer", "", text, True)
        device.play(tts.stream(text, profile), tts.sample_rate)
        device.plate("idle")
        return "ok"

    def demo(self, name: str, voice: bool, scale: float = 1.0, theme: str | None = None) -> str:
        theme = theme or self.brain.settings.theme(name)
        base = self.sender(name)
        send = lambda phase, request="", answer="", voice=True, window=0: base(phase, request, answer, voice, theme, window)
        words = DEMO_REQUEST.split()
        send("listening", "", "", voice)
        time.sleep(0.9 * scale)
        for index in range(1, len(words) + 1):
            send("listening", " ".join(words[:index]), "", voice)
            time.sleep(0.4 * scale)
        send("thinking", DEMO_REQUEST, "", voice)
        time.sleep(1.3 * scale)
        send("answer", DEMO_REQUEST, DEMO_ANSWER, voice)
        time.sleep(4.5 * scale)
        send("followup", DEMO_REQUEST, DEMO_ANSWER, voice, 3.5 * scale)
        time.sleep(3.5 * scale)
        send("idle", "", "", voice)
        return "ok"

    def control(self, connection) -> None:
        for message in connection:
            request = json.loads(message)
            kind = request.get("type")
            name = str(request.get("device", "tv"))
            if kind == "levels":
                levels = {
                    key: {"peak": getattr(d, "peak", 0), "rms": round(getattr(d, "rms", 0.0), 1), "alive": d.alive}
                    for key, d in self.devices.items()
                }
                result = levels
            elif kind == "ask":
                try:
                    result = self.brain.assistant.handle(str(request.get("text", "")), name)
                except Exception as error:
                    result = f"ошибка: {error}"
            elif kind == "set_style":
                self.brain.settings.set_style(name, str(request.get("style", "plate")))
                result = self.brain.settings.style(name)
            elif kind == "announce":
                result = self.announce(name, str(request.get("text", "")), request.get("voice"))
            elif kind == "music_play":
                try:
                    result = self.music.play(str(request.get("query", "")), str(request.get("kind", "auto")), name, request.get("volume"))
                except Exception as error:
                    result = f"ошибка: {error}"
            elif kind == "music_control":
                try:
                    result = self.music.control(str(request.get("action", "")), name)
                except Exception as error:
                    result = f"ошибка: {error}"
            elif kind == "demo":
                result = self.demo(name, bool(request.get("voice", True)), float(request.get("scale", 1.0)), request.get("theme"))
            else:
                continue
            connection.send(json.dumps({"type": "result", "result": result}, ensure_ascii=False))

    def display(self, connection, name: str) -> None:
        self.displays.add(name, connection)
        try:
            connection.send(json.dumps(self.brain.settings.snapshot(name)))
            connection.send(json.dumps(self.brain.assistant.music.card_payload(name), ensure_ascii=False))
            for message in connection:
                request = json.loads(message)
                if request.get("type") == "set_voice":
                    self.brain.settings.set_voice(name, bool(request.get("enabled")))
                elif request.get("type") == "set_theme":
                    self.brain.settings.set_theme(name, str(request.get("theme", "dark")))
                elif request.get("type") == "set_indicator":
                    self.brain.settings.set_indicator(name, str(request.get("style", "classic")))
                elif request.get("type") == "music_stop":
                    for device in list(self.devices):
                        try:
                            self.music.control("stop", device)
                        except Exception as error:
                            print(f"[музыка] {device}: {error}", flush=True)
                elif request.get("type") == "set_volume":
                    self.brain.settings.set_volume(name, int(request.get("percent", 100)))
        finally:
            self.displays.remove(name, connection)

    def handle(self, connection) -> None:
        try:
            hello = json.loads(connection.recv(timeout=10))
        except Exception:
            return
        if hello.get("type") != "hello" or not secrets.compare_digest(str(hello.get("token", "")), self.token):
            connection.close(code=4401, reason="bad token")
            return
        role = hello.get("role")
        if role == "control":
            self.control(connection)
            return
        name = str(hello.get("device") or "tv")[:32]
        if not self.brain.settings.enabled(name):
            connection.close(code=4403, reason="device disabled")
            return
        if role == "display":
            self.display(connection, name)
            return
        device = RemoteDevice(name, connection, self.cfg["audio"]["preroll_seconds"], int(hello.get("rate", 16000)))
        self.devices[name] = device
        device.style_provider = lambda: self.brain.settings.style(name)
        device.music_listener = lambda message: self.music.on_event(name, message)
        print(f"[{name}] подключено", flush=True)
        Listener(device, self.brain).start()
        try:
            for message in connection:
                if isinstance(message, bytes):
                    device.feed(message)
                else:
                    device.on_text(json.loads(message))
        except Exception:
            pass
        finally:
            device.closed.set()

    def run(self) -> None:
        network = self.cfg["network"]
        with serve(self.handle, network["host"], network["port"], max_size=2**20) as server:
            print(f"Жду устройства на порту {network['port']}", flush=True)
            server.serve_forever()
