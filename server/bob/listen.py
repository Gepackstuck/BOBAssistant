import numpy as np
import torch
from silero_vad import load_silero_vad


WINDOW = 512


class Vad:
    def __init__(self, threshold: float):
        self.model = load_silero_vad(onnx=True)
        self.threshold = threshold

    def speech_ratio(self, block: np.ndarray, sample_rate: int) -> float:
        audio = torch.from_numpy(block.astype(np.float32) / 32768)
        windows = [audio[i:i + WINDOW] for i in range(0, len(audio) - WINDOW + 1, WINDOW)]
        voiced = sum(1 for w in windows if self.model(w, sample_rate).item() >= self.threshold)
        return voiced / max(1, len(windows))

    def reset(self) -> None:
        self.model.reset_states()


def capture(mic, vad: Vad, cfg: dict, preroll: list[np.ndarray], start_timeout: float | None = None, on_block=None, min_speech: float = 0.0) -> tuple[np.ndarray, bool]:
    rate = mic.sample_rate
    block_ms = 1000 * len(preroll[0]) / rate if preroll else 80
    silence_limit = cfg["silence_ms"] / block_ms
    start_limit = (start_timeout or cfg["start_timeout_seconds"]) * 1000 / block_ms
    max_blocks = cfg["max_seconds"] * 1000 / block_ms
    vad.reset()
    blocks = list(preroll)
    if on_block:
        for block in preroll:
            on_block(block)
    heard = any(vad.speech_ratio(block, rate) > 0.3 for block in preroll)
    vad.reset()
    heard_before = heard
    heard = False
    quiet = 0
    waited = 0
    voiced_ms = 0.0
    while len(blocks) < max_blocks:
        block = mic.read(timeout=1)
        if block is None:
            break
        blocks.append(block)
        if on_block:
            on_block(block)
        if vad.speech_ratio(block, rate) > 0.3:
            voiced_ms += block_ms
            quiet = 0
            heard = heard or voiced_ms >= min_speech * 1000
        elif heard:
            quiet += 1
            if quiet >= silence_limit:
                break
        else:
            waited += 1
            if waited >= start_limit:
                break
    audio = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.int16)
    return audio, heard or heard_before
