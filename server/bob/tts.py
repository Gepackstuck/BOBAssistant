import re
from typing import Iterator

import numpy as np
import torch

from .config import resolve
from .models import ensure_file
from .textnorm import for_speech

SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
MAX_CHARS = 900


class SileroTts:
    def __init__(self, cfg: dict):
        path = ensure_file(resolve(cfg["model_path"]), cfg["model_url"])
        torch.set_num_threads(4)
        self.model = torch.package.PackageImporter(str(path)).load_pickle("tts_models", "model")
        self.sample_rate = cfg["sample_rate"]
        self.voices: dict[str, dict] = cfg["voices"]
        self.by_wake: dict[str, str] = cfg.get("by_wake", {})
        self.default_voice: str = cfg["default_voice"]

    def voice_for(self, wake_key: str | None) -> dict:
        return self.voices[self.by_wake.get(wake_key or "", self.default_voice)]

    def _chunks(self, text: str) -> list[str]:
        return [
            part
            for part in (s.strip()[:MAX_CHARS] for s in SENTENCE_RE.split(text))
            if re.search(r"\w", part)
        ]

    def _say(self, chunk: str, voice: dict) -> np.ndarray:
        audio = self.model.apply_tts(
            text=chunk,
            speaker=voice["speaker"],
            sample_rate=self.sample_rate,
            put_accent=True,
            put_yo=True,
        ).numpy().astype(np.float32)
        speed = voice.get("speed", 1.0)
        if speed == 1.0:
            return audio
        positions = np.arange(0, len(audio) - 1, speed)
        return np.interp(positions, np.arange(len(audio)), audio).astype(np.float32)

    def stream(self, text: str, voice: dict | None = None) -> Iterator[np.ndarray]:
        chosen = voice or self.voices[self.default_voice]
        return (self._say(chunk, chosen) for chunk in self._chunks(for_speech(text)))

    def synth(self, text: str, voice: dict | None = None) -> np.ndarray:
        parts = list(self.stream(text, voice))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
