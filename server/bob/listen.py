import numpy as np
import torch
from silero_vad import load_silero_vad

from .audio import Mic

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


def capture(mic: Mic, vad: Vad, cfg: dict, preroll: list[np.ndarray]) -> tuple[np.ndarray, bool]:
    rate = mic.sample_rate
    block_ms = 1000 * len(preroll[0]) / rate if preroll else 80
    silence_limit = cfg["silence_ms"] / block_ms
    start_limit = cfg["start_timeout_seconds"] * 1000 / block_ms
    max_blocks = cfg["max_seconds"] * 1000 / block_ms
    vad.reset()
    blocks = list(preroll)
    heard = any(vad.speech_ratio(block, rate) > 0.3 for block in preroll)
    vad.reset()
    heard_before = heard
    heard = False
    quiet = 0
    waited = 0
    while len(blocks) < max_blocks:
        block = mic.read(timeout=1)
        if block is None:
            break
        blocks.append(block)
        if vad.speech_ratio(block, rate) > 0.3:
            heard, quiet = True, 0
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
