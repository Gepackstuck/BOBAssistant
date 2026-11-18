import re

import mlx_whisper
import numpy as np

NO_SPEECH_LIMIT = 0.6
CONFIDENCE_LIMIT = -1.2
HALLUCINATION_RE = re.compile(
    r"субтитр|DimaTorzok|продолжение следует|спасибо за просмотр|подписывайтесь на канал|редактор субтитров|корректор",
    re.IGNORECASE,
)


class Whisper:
    def __init__(self, cfg: dict):
        self.model = cfg["model"]
        self.language = cfg["language"]
        self.prompt = cfg.get("prompt")
        self.names: set[str] = set()
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
        segments = [
            segment for segment in result.get("segments", [])
            if segment.get("no_speech_prob", 0) <= NO_SPEECH_LIMIT and segment.get("avg_logprob", 0) >= CONFIDENCE_LIMIT
        ]
        text = " ".join(segment["text"].strip() for segment in segments).strip() if "segments" in result else result.get("text", "").strip()
        return "" if HALLUCINATION_RE.search(text) or self.echoes_prompt(text) else text

    def echoes_prompt(self, text: str) -> bool:
        parts = [part.strip(" .!?«»").lower() for part in re.split(r"[,;]", text) if part.strip(" .!?«»")]
        known = sum(1 for part in parts if part in self.names)
        return known >= 4 and known >= 0.7 * len(parts)
