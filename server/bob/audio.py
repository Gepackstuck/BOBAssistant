import queue
import time
from collections import deque
from typing import Iterable

import numpy as np
import sounddevice as sd

BLOCK = 1280
WATCHDOG_SECONDS = 3.0


BUILTIN_NAMES = ("macbook", "imac", "mac mini", "mac studio", "mac pro", "built-in", "встроенный")


def builtin_input() -> int | None:
    return next(
        (
            index
            for index, info in enumerate(sd.query_devices())
            if info["max_input_channels"] > 0 and any(name in info["name"].lower() for name in BUILTIN_NAMES)
        ),
        None,
    )


class Mic:
    def __init__(self, sample_rate: int, device: str | int | None, preroll_seconds: float):
        self.sample_rate = sample_rate
        self.frames: queue.Queue[np.ndarray] = queue.Queue()
        self.preroll: deque[np.ndarray] = deque(maxlen=max(1, int(preroll_seconds * sample_rate / BLOCK)))
        self.muted = False
        self.device = device
        self.last_callback = time.monotonic()
        self.peak = 0
        self.rms = 0.0
        self.restarts = 0
        self.stream = self._open()

    def _open(self) -> sd.InputStream:
        return sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=BLOCK,
            device=builtin_input() if self.device == "builtin" else self.device,
            callback=self._callback,
        )

    def _callback(self, data, frames, moment, status) -> None:
        self.last_callback = time.monotonic()
        samples = data[:, 0]
        self.peak = max(int(np.abs(samples).max()), int(self.peak * 0.97))
        self.rms = 0.95 * self.rms + 0.05 * float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        if not self.muted:
            self.frames.put(samples.copy())

    def __enter__(self) -> "Mic":
        self.stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stream.stop()
        self.stream.close()

    def restart(self) -> None:
        print("[mac] микрофон замолчал, открываю заново", flush=True)
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
        self.stream = self._open()
        self.stream.start()
        self.restarts += 1
        self.last_callback = time.monotonic()

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        try:
            block = self.frames.get(timeout=timeout)
        except queue.Empty:
            if time.monotonic() - self.last_callback > WATCHDOG_SECONDS:
                try:
                    self.restart()
                except Exception as error:
                    print(f"[mac] не удалось открыть микрофон: {error}", flush=True)
                    self.last_callback = time.monotonic()
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


class Speaker:
    def __init__(self, device: str | int | None, mic: Mic | None = None):
        self.device = device
        self.mic = mic

    def play(self, samples: np.ndarray, sample_rate: int) -> None:
        if self.mic:
            self.mic.muted = True
        try:
            sd.play(samples, sample_rate, device=self.device)
            sd.wait()
        finally:
            if self.mic:
                self.mic.drain()
                self.mic.muted = False

    def play_stream(self, chunks: Iterable[np.ndarray], sample_rate: int) -> None:
        if self.mic:
            self.mic.muted = True
        try:
            for samples in chunks:
                sd.wait()
                sd.play(samples, sample_rate, device=self.device)
            sd.wait()
        finally:
            if self.mic:
                self.mic.drain()
                self.mic.muted = False

    def chime(self) -> None:
        rate = 48000
        t = np.linspace(0, 0.12, int(rate * 0.12), endpoint=False)
        envelope = np.minimum(1, np.minimum(t / 0.01, (0.12 - t) / 0.04))
        tone = 0.25 * envelope * (np.sin(2 * np.pi * 880 * t) + 0.5 * np.sin(2 * np.pi * 1320 * t))
        self.play(tone.astype(np.float32), rate)
