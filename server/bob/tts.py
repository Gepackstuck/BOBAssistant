import re
from typing import Iterator

import numpy as np
import torch
from fractions import Fraction
from scipy.signal import resample_poly

from .config import resolve
from .models import ensure_file
from .textnorm import for_speech

SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
CLAUSE_RE = re.compile(r"(?<=[,;:—])\s+")
MAX_CHARS = 900
PIECE_CHARS = 110
SENTENCE_PAUSE = 0.45
CLAUSE_PAUSE = 0.22
TAIL_PAUSE = 0.5


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

    def _pieces(self, sentence: str) -> list[str]:
        pieces: list[str] = []
        for clause in CLAUSE_RE.split(sentence):
            if pieces and len(pieces[-1]) + len(clause) < PIECE_CHARS and not pieces[-1].endswith((";", ":")):
                pieces[-1] = f"{pieces[-1]} {clause}"
            else:
                pieces.append(clause)
        return pieces

    def _chunks(self, text: str) -> list[tuple[str, float]]:
        chunks: list[tuple[str, float]] = []
        for sentence in (part.strip()[:MAX_CHARS] for part in SENTENCE_RE.split(text)):
            if not re.search(r"\w", sentence):
                continue
            pieces = self._pieces(sentence) if len(sentence) > PIECE_CHARS else [sentence]
            chunks.extend((piece, CLAUSE_PAUSE) for piece in pieces[:-1])
            chunks.append((pieces[-1], SENTENCE_PAUSE))
        return chunks

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
        up, down = Fraction(speed).limit_denominator(20).denominator, Fraction(speed).limit_denominator(20).numerator
        return resample_poly(audio, up, down).astype(np.float32)

    def stream(self, text: str, voice: dict | None = None) -> Iterator[np.ndarray]:
        chosen = voice or self.voices[self.default_voice]
        chunks = self._chunks(for_speech(text))
        for index, (chunk, pause) in enumerate(chunks):
            last = index == len(chunks) - 1
            audio = self._say(chunk if re.search(r"[.!?…,;:]$", chunk) else chunk + ".", chosen)
            yield np.concatenate([audio, np.zeros(int(self.sample_rate * (TAIL_PAUSE if last else pause)), dtype=np.float32)])

    def synth(self, text: str, voice: dict | None = None) -> np.ndarray:
        parts = list(self.stream(text, voice))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
