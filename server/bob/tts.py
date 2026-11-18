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
        self.speaker = cfg["speaker"]
        self.sample_rate = cfg["sample_rate"]

    def _chunks(self, text: str) -> list[str]:
        return [
            part
            for part in (s.strip()[:MAX_CHARS] for s in SENTENCE_RE.split(text))
            if re.search(r"\w", part)
        ]

    def _say(self, chunk: str) -> np.ndarray:
        return self.model.apply_tts(
            text=chunk,
            speaker=self.speaker,
            sample_rate=self.sample_rate,
            put_accent=True,
            put_yo=True,
        ).numpy().astype(np.float32)

    def stream(self, text: str) -> Iterator[np.ndarray]:
        return (self._say(chunk) for chunk in self._chunks(for_speech(text)))

    def synth(self, text: str) -> np.ndarray:
        parts = list(self.stream(text))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
