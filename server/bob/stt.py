import re

import mlx_whisper
import numpy as np

HALLUCINATION_RE = re.compile(
    r"субтитр|DimaTorzok|продолжение следует|спасибо за просмотр|подписывайтесь на канал|редактор субтитров|корректор",
    re.IGNORECASE,
)


class Whisper:
    def __init__(self, cfg: dict):
        self.model = cfg["model"]
        self.language = cfg["language"]
        self.prompt = cfg.get("prompt")
        self.transcribe(np.zeros(16000, dtype=np.int16))

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        result = mlx_whisper.transcribe(
            audio.astype(np.float32) / 32768,
            path_or_hf_repo=self.model,
            language=self.language,
            initial_prompt=self.prompt,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
        text = result.get("text", "").strip()
        return "" if HALLUCINATION_RE.search(text) else text
