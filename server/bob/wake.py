import json
import re

import numpy as np
from vosk import KaldiRecognizer, Model, SetLogLevel

from .config import resolve
from .models import ensure_zip_dir

WAKE_RE = re.compile(
    r"(?:о?кей|ок|okay|ok)[\s,.!-]*сбер\w*|минь?он\w*|подручн\w*|\bбоб\w*",
    re.IGNORECASE,
)


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
        self.triggers = [tuple(trigger) for trigger in cfg["triggers"]]
        self.reset()

    def reset(self) -> None:
        self.recognizer = KaldiRecognizer(self.model, self.sample_rate, self.grammar)

    def _match(self, text: str) -> str | None:
        words = text.split()
        return next(
            (
                " ".join(trigger)
                for trigger in self.triggers
                for i in range(len(words) - len(trigger) + 1)
                if tuple(words[i:i + len(trigger)]) == trigger
            ),
            None,
        )

    def feed(self, block: np.ndarray) -> str | None:
        if self.recognizer.AcceptWaveform(block.tobytes()):
            text = json.loads(self.recognizer.Result()).get("text", "")
        else:
            text = json.loads(self.recognizer.PartialResult()).get("partial", "")
        found = self._match(text)
        if found:
            self.reset()
        return found
