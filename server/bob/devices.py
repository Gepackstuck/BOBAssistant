import json
import queue
import threading
from collections import deque
from typing import Iterable

import numpy as np

from .audio import BLOCK, Mic, Speaker


class Device:
    name = "device"
    sample_rate = 16000

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        raise NotImplementedError

    def take_preroll(self) -> list[np.ndarray]:
        raise NotImplementedError

    def drain(self) -> None:
        raise NotImplementedError

    def show(self, state: str, text: str = "") -> None:
        return None

    def chime(self) -> None:
        return None

    def play(self, chunks: Iterable[np.ndarray], rate: int) -> None:
        raise NotImplementedError

    @property
    def alive(self) -> bool:
        return True


class LocalDevice(Device):
    def __init__(self, name: str, mic: Mic, speaker: Speaker):
        self.name = name
        self.mic = mic
        self.speaker = speaker
        self.sample_rate = mic.sample_rate

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        return self.mic.read(timeout)

    def take_preroll(self) -> list[np.ndarray]:
        return self.mic.take_preroll()

    def drain(self) -> None:
        self.mic.drain()

    def chime(self) -> None:
        self.speaker.chime()

    def play(self, chunks: Iterable[np.ndarray], rate: int) -> None:
        self.speaker.play_stream(chunks, rate)


class RemoteDevice(Device):
    def __init__(self, name: str, connection, preroll_seconds: float, sample_rate: int = 16000):
        self.name = name
        self.connection = connection
        self.sample_rate = sample_rate
        self.frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)
        self.preroll: deque[np.ndarray] = deque(maxlen=max(1, int(preroll_seconds * sample_rate / BLOCK)))
        self.pending = np.zeros(0, dtype=np.int16)
        self.muted = threading.Event()
        self.closed = threading.Event()
        self.send_lock = threading.Lock()

    def feed(self, payload: bytes) -> None:
        if self.muted.is_set():
            return
        self.pending = np.concatenate([self.pending, np.frombuffer(payload, dtype="<i2")])
        while len(self.pending) >= BLOCK:
            block, self.pending = self.pending[:BLOCK].copy(), self.pending[BLOCK:]
            if self.frames.full():
                self.frames.get_nowait()
            self.frames.put(block)

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        try:
            block = self.frames.get(timeout=timeout)
        except queue.Empty:
            return None
        self.preroll.append(block)
        return block

    def take_preroll(self) -> list[np.ndarray]:
        blocks = list(self.preroll)
        self.preroll.clear()
        return blocks

    def drain(self) -> None:
        while not self.frames.empty():
            self.frames.get_nowait()
        self.preroll.clear()
        self.pending = np.zeros(0, dtype=np.int16)

    def _send(self, message) -> None:
        if self.closed.is_set():
            return
        try:
            with self.send_lock:
                self.connection.send(message)
        except Exception:
            self.closed.set()

    def show(self, state: str, text: str = "") -> None:
        self._send(json.dumps({"type": "state", "state": state, "text": text}, ensure_ascii=False))

    def chime(self) -> None:
        self._send(json.dumps({"type": "chime"}))

    def play(self, chunks: Iterable[np.ndarray], rate: int) -> None:
        self.muted.set()
        try:
            self._send(json.dumps({"type": "audio_start", "rate": rate}))
            for chunk in chunks:
                pcm = (np.clip(chunk, -1, 1) * 32767).astype("<i2").tobytes()
                for i in range(0, len(pcm), 32768):
                    self._send(pcm[i:i + 32768])
            self._send(json.dumps({"type": "audio_end"}))
            self._wait_played()
        finally:
            self.drain()
            self.muted.clear()

    def _wait_played(self) -> None:
        self.played = threading.Event()
        self.played.wait(timeout=60)

    def on_text(self, message: dict) -> None:
        if message.get("type") == "played" and getattr(self, "played", None):
            self.played.set()

    @property
    def alive(self) -> bool:
        return not self.closed.is_set()
