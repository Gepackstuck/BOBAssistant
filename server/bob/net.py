import json
import os
import secrets
import threading

from websockets.sync.server import serve

from .config import ROOT
from .devices import RemoteDevice
from .pipeline import Brain, Listener

TOKEN_FILE = ROOT / "secrets" / "token"


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
    def __init__(self, cfg: dict, brain: Brain):
        super().__init__(daemon=True, name="device-server")
        self.cfg = cfg
        self.brain = brain
        self.token = device_token(cfg)

    def handle(self, connection) -> None:
        try:
            hello = json.loads(connection.recv(timeout=10))
        except Exception:
            return
        if hello.get("type") != "hello" or not secrets.compare_digest(str(hello.get("token", "")), self.token):
            connection.close(code=4401, reason="bad token")
            return
        name = str(hello.get("device") or "tv")[:32]
        device = RemoteDevice(name, connection, self.cfg["audio"]["preroll_seconds"], int(hello.get("rate", 16000)))
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
