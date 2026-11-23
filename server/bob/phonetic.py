import json
import queue
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

from .config import ROOT

HELPER = ROOT / "helpers" / "gigaam"
TIMEOUT = 20


class Phonetic:
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.lines: queue.Queue[str] = queue.Queue()
        self.ready = threading.Event()
        self.lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.ready.is_set()

    @property
    def installed(self) -> bool:
        return (HELPER / ".venv" / "bin" / "python").exists()

    def start(self) -> None:
        if not self.installed or self.process is not None:
            return
        self.process = subprocess.Popen(
            [str(HELPER / ".venv" / "bin" / "python"), str(HELPER / "worker.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=str(HELPER),
        )
        threading.Thread(target=self.read, daemon=True, name="gigaam-reader").start()

    def read(self) -> None:
        for line in self.process.stdout:
            line = line.strip()
            if line.startswith("{"):
                if json.loads(line).get("ready"):
                    self.ready.set()
                else:
                    self.lines.put(line)

    def transcribe(self, audio: np.ndarray, rate: int = 16000) -> str:
        if not self.ready.is_set() or audio.size == 0:
            return ""
        with self.lock:
            with tempfile.NamedTemporaryFile(suffix=".wav") as file:
                with wave.open(file.name, "wb") as out:
                    out.setnchannels(1)
                    out.setsampwidth(2)
                    out.setframerate(rate)
                    out.writeframes(audio.astype("int16").tobytes())
                while not self.lines.empty():
                    self.lines.get_nowait()
                self.process.stdin.write(json.dumps({"wav": file.name}) + "\n")
                self.process.stdin.flush()
                try:
                    return json.loads(self.lines.get(timeout=TIMEOUT)).get("text", "")
                except queue.Empty:
                    return ""

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
