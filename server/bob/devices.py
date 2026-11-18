import json
import queue
import threading
from collections import deque
from typing import Iterable

import numpy as np

from .audio import BLOCK, Mic, Speaker
from .macplayer import MacPlayer


class Displays:
    def __init__(self):
        self.lock = threading.Lock()
        self.connections: dict[str, set] = {}

    def add(self, name: str, connection) -> None:
        with self.lock:
            self.connections.setdefault(name, set()).add(connection)

    def remove(self, name: str, connection) -> None:
        with self.lock:
            self.connections.get(name, set()).discard(connection)

    def publish(self, name: str, payload: dict) -> None:
        with self.lock:
            targets = list(self.connections.get(name, ()))
        for connection in targets:
            try:
                connection.send(json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass


def plate_payload(phase: str, request: str, answer: str, voice: bool, theme: str = "dark", window: float = 0) -> dict:
    return {"type": "plate", "phase": phase, "request": request, "answer": answer, "voice": voice, "theme": theme, "window": window}


class Device:
    name = "device"
    sample_rate = 16000

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        raise NotImplementedError

    def take_preroll(self) -> list[np.ndarray]:
        raise NotImplementedError

    def drain(self) -> None:
        raise NotImplementedError

    def plate(self, phase: str, request: str = "", answer: str = "", voice: bool = True, theme: str = "dark", window: float = 0) -> None:
        return None

    def media(self, hold: bool) -> None:
        return None

    def card(self, payload: dict) -> None:
        return None

    def chime(self) -> None:
        return None

    def music(self, payload: dict) -> None:
        return None

    def play(self, chunks: Iterable[np.ndarray], rate: int, monitor=None) -> str | None:
        raise NotImplementedError

    @property
    def alive(self) -> bool:
        return True


class LocalDevice(Device):
    def __init__(self, name: str, mic: Mic, speaker: Speaker, displays: Displays):
        self.name = name
        self.mic = mic
        self.speaker = speaker
        self.displays = displays
        self.sample_rate = mic.sample_rate
        self.music_listener = None
        self.player = MacPlayer(lambda event: self.music_listener and self.music_listener({"event": event}))

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        return self.mic.read(timeout)

    def take_preroll(self) -> list[np.ndarray]:
        return self.mic.take_preroll()

    def drain(self) -> None:
        self.mic.drain()

    def plate(self, phase: str, request: str = "", answer: str = "", voice: bool = True, theme: str = "dark", window: float = 0) -> None:
        self.displays.publish(self.name, plate_payload(phase, request, answer, voice, theme, window))

    def music(self, payload: dict) -> None:
        self.player.handle(payload)

    def card(self, payload: dict) -> None:
        self.displays.publish(self.name, payload)

    @property
    def peak(self) -> int:
        return self.mic.peak

    @property
    def rms(self) -> float:
        return self.mic.rms

    def chime(self) -> None:
        self.speaker.chime()

    def play(self, chunks: Iterable[np.ndarray], rate: int, monitor=None) -> str | None:
        return self.speaker.play_stream(chunks, rate, monitor)


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
        self.played = threading.Event()
        self.music_listener = None
        self.peak = 0
        self.rms = 0.0

    def feed(self, payload: bytes) -> None:
        if self.muted.is_set():
            return
        samples = np.frombuffer(payload, dtype="<i2")
        if samples.size:
            self.peak = max(int(np.abs(samples).max()), int(self.peak * 0.97))
            self.rms = 0.95 * self.rms + 0.05 * float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        self.pending = np.concatenate([self.pending, samples])
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

    def plate(self, phase: str, request: str = "", answer: str = "", voice: bool = True, theme: str = "dark", window: float = 0) -> None:
        self._send(json.dumps(plate_payload(phase, request, answer, voice, theme, window), ensure_ascii=False))

    def media(self, hold: bool) -> None:
        self._send(json.dumps({"type": "media", "hold": hold}))

    def chime(self) -> None:
        self._send(json.dumps({"type": "chime"}))

    def music(self, payload: dict) -> None:
        self._send(json.dumps({"type": "music", **payload}))

    def play(self, chunks: Iterable[np.ndarray], rate: int, monitor=None) -> str | None:
        self.muted.set()
        self.played.clear()
        try:
            self._send(json.dumps({"type": "audio_start", "rate": rate}))
            for chunk in chunks:
                pcm = (np.clip(chunk, -1, 1) * 32767).astype("<i2").tobytes()
                for i in range(0, len(pcm), 32768):
                    self._send(pcm[i:i + 32768])
            self._send(json.dumps({"type": "audio_end"}))
            self.played.wait(timeout=60)
        finally:
            self.drain()
            self.muted.clear()

    def on_text(self, message: dict) -> None:
        if message.get("type") == "played":
            self.played.set()
        elif message.get("type") == "music_event" and self.music_listener:
            self.music_listener(message)

    @property
    def alive(self) -> bool:
        return not self.closed.is_set()
