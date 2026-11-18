import queue
from collections import deque

import numpy as np
import sounddevice as sd

BLOCK = 1280


class Mic:
    def __init__(self, sample_rate: int, device: str | int | None, preroll_seconds: float):
        self.sample_rate = sample_rate
        self.frames: queue.Queue[np.ndarray] = queue.Queue()
        self.preroll: deque[np.ndarray] = deque(maxlen=max(1, int(preroll_seconds * sample_rate / BLOCK)))
        self.muted = False
        self.stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=BLOCK,
            device=device,
            callback=self._callback,
        )

    def _callback(self, data, frames, time, status) -> None:
        if not self.muted:
            self.frames.put(data[:, 0].copy())

    def __enter__(self) -> "Mic":
        self.stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stream.stop()
        self.stream.close()

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

    def chime(self) -> None:
        rate = 48000
        t = np.linspace(0, 0.12, int(rate * 0.12), endpoint=False)
        envelope = np.minimum(1, np.minimum(t / 0.01, (0.12 - t) / 0.04))
        tone = 0.25 * envelope * (np.sin(2 * np.pi * 880 * t) + 0.5 * np.sin(2 * np.pi * 1320 * t))
        self.play(tone.astype(np.float32), rate)
