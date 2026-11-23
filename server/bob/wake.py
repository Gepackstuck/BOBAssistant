import json
import re

import numpy as np
from vosk import KaldiRecognizer, Model, SetLogLevel

from .config import resolve
from .models import ensure_zip_dir

WAKE_RE = re.compile(
    r"д?ж[аеэи]р[вб]?[иеэы]с\w*",
    re.IGNORECASE,
)


STRONG_WAIT_BLOCKS = 6
GIGA_WAKE_RE = re.compile(r"ж[аеэи]р[вб]?[иеэы]с|ярвис", re.IGNORECASE)


def normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


PUNCT = " \t\n,.!?-—:;«»\"'"
SENTENCE_END_RE = re.compile(r"[.!?…]")


def strip_wake(text: str) -> tuple[bool, str]:
    matches = list(WAKE_RE.finditer(normalize(text)))
    if not matches:
        return False, text.strip()
    last = matches[-1]
    after = text[last.end():].strip(PUNCT)
    if after:
        return True, after
    before = text[:last.start()]
    sentence_start = max((m.end() for m in SENTENCE_END_RE.finditer(before)), default=0)
    return True, WAKE_RE.sub("", before[sentence_start:]).strip(PUNCT)


def remove_wake(text: str) -> str:
    return re.sub(r"\s{2,}", " ", WAKE_RE.sub("", text)).strip(PUNCT)


class VoskWake:
    def __init__(self, cfg: dict, sample_rate: int):
        SetLogLevel(-1)
        model_dir = ensure_zip_dir(resolve(cfg["vosk_model"]), cfg["vosk_url"])
        self.model = Model(str(model_dir))
        self.sample_rate = sample_rate
        self.grammar = json.dumps([*cfg["grammar"], "[unk]"], ensure_ascii=False)
        decoys = cfg.get("decoys", [])
        self.strong_grammar = json.dumps([*cfg["grammar"], *decoys, "[unk]"], ensure_ascii=False) if decoys else None
        self.strong = False
        self.pending: tuple[str, int] | None = None
        self.triggers = [
            (key, tuple(tokens))
            for key, variants in cfg["triggers"].items()
            for tokens in variants
        ]
        self.reset()

    def reset(self) -> None:
        self.pending = None
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate, self.grammar)
        self.decoy_recognizer = KaldiRecognizer(self.model, self.sample_rate, self.strong_grammar) if self.strong_grammar else None

    def live(self) -> "LiveSpeech":
        return LiveSpeech(self.model, self.sample_rate)

    def _match(self, text: str) -> str | None:
        words = text.split()
        return next(
            (
                key
                for key, tokens in self.triggers
                for i in range(len(words) - len(tokens) + 1)
                if tuple(words[i:i + len(tokens)]) == tokens
            ),
            None,
        )

    def _decode(self, recognizer, block: np.ndarray) -> str:
        if recognizer.AcceptWaveform(block.tobytes()):
            return json.loads(recognizer.Result()).get("text", "")
        return json.loads(recognizer.PartialResult()).get("partial", "")

    def feed(self, block: np.ndarray) -> str | None:
        found = self._match(self._decode(self.recognizer, block))
        strong = self._match(self._decode(self.decoy_recognizer, block)) if self.decoy_recognizer else None
        if strong:
            self.strong = True
            self.reset()
            return strong
        if self.pending is not None:
            key, left = self.pending
            if left <= 1:
                self.strong = False
                self.reset()
                return key
            self.pending = (key, left - 1)
            return None
        if found:
            if not self.decoy_recognizer:
                self.strong = False
                self.reset()
                return found
            self.pending = (found, STRONG_WAIT_BLOCKS)
        return None


class LiveSpeech:
    def __init__(self, model, sample_rate: int):
        self.recognizer = KaldiRecognizer(model, sample_rate)
        self.finished: list[str] = []
        self.partial = ""

    def feed(self, block: np.ndarray) -> str:
        if self.recognizer.AcceptWaveform(block.tobytes()):
            text = json.loads(self.recognizer.Result()).get("text", "")
            if text:
                self.finished.append(text)
            self.partial = ""
        else:
            self.partial = json.loads(self.recognizer.PartialResult()).get("partial", "")
        return " ".join([*self.finished, self.partial]).strip()


def make_wake(cfg: dict, sample_rate: int):
    return VoskWake(cfg, sample_rate)
