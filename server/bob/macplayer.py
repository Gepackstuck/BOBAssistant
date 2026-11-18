import os
import signal
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

import httpx


class MacPlayer:
    def __init__(self, on_event: Callable[[str], None]):
        self.on_event = on_event
        self.process: subprocess.Popen | None = None
        self.file: Path | None = None
        self.generation = 0
        self.volume = 0.8
        self.lock = threading.Lock()

    def handle(self, payload: dict) -> None:
        action = payload.get("action")
        if action == "play":
            self.play(payload["url"], float(payload.get("volume", self.volume)))
        elif action == "pause":
            self.signal(signal.SIGSTOP)
        elif action == "resume":
            self.signal(signal.SIGCONT)
        elif action == "stop":
            self.stop()
        elif action == "volume":
            self.volume = float(payload.get("volume", self.volume))

    def signal(self, sig: int) -> None:
        with self.lock:
            if self.process and self.process.poll() is None:
                os.kill(self.process.pid, sig)

    def stop(self) -> None:
        with self.lock:
            self.generation += 1
            process, self.process = self.process, None
        if process and process.poll() is None:
            os.kill(process.pid, signal.SIGKILL)
        if self.file and self.file.exists():
            self.file.unlink(missing_ok=True)

    def play(self, url: str, volume: float) -> None:
        self.stop()
        self.volume = volume
        with self.lock:
            generation = self.generation
        threading.Thread(target=self.run, args=(url, volume, generation), daemon=True).start()

    def run(self, url: str, volume: float, generation: int) -> None:
        handle, name = tempfile.mkstemp(suffix=".mp3", prefix="bob-")
        os.close(handle)
        path = Path(name)
        try:
            with httpx.stream("GET", url, timeout=30, follow_redirects=True) as response:
                response.raise_for_status()
                with path.open("wb") as out:
                    for chunk in response.iter_bytes(1 << 16):
                        out.write(chunk)
        except Exception:
            path.unlink(missing_ok=True)
            self.on_event("error")
            return
        with self.lock:
            if generation != self.generation:
                path.unlink(missing_ok=True)
                return
            self.file = path
            self.process = subprocess.Popen(["afplay", "-v", f"{volume:.2f}", str(path)])
            process = self.process
        process.wait()
        path.unlink(missing_ok=True)
        with self.lock:
            current = generation == self.generation
        if current and process.returncode == 0:
            self.on_event("ended")
