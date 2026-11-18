from pathlib import Path

import numpy as np
import yaml
from scipy.signal import fftconvolve, resample, resample_poly

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RATE = 16000


def load_words() -> dict:
    return yaml.safe_load((ROOT / "words.yaml").read_text(encoding="utf-8"))


def save_clips(path: Path, clips: list[np.ndarray], voices: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lengths = np.array([len(c) for c in clips])
    np.savez_compressed(
        path,
        audio=np.concatenate(clips).astype(np.int16) if clips else np.zeros(0, np.int16),
        offsets=np.concatenate([[0], np.cumsum(lengths)]),
        voices=np.array(voices),
    )


def load_clips(path: Path) -> tuple[list[np.ndarray], list[str]]:
    with np.load(path) as data:
        audio, offsets, voices = data["audio"], data["offsets"], list(data["voices"])
    return [audio[a:b].copy() for a, b in zip(offsets[:-1], offsets[1:])], voices


def to_16k(audio: np.ndarray, rate: int) -> np.ndarray:
    if rate == RATE:
        return audio.astype(np.float32)
    divisor = np.gcd(rate, RATE)
    return resample_poly(audio.astype(np.float32), RATE // divisor, rate // divisor)


def trim_silence(audio: np.ndarray, threshold: float = 0.02) -> np.ndarray:
    loud = np.flatnonzero(np.abs(audio) > threshold * np.abs(audio).max())
    if loud.size == 0:
        return audio
    return audio[max(0, loud[0] - 800):loud[-1] + 800]


def colored_noise(rng: np.random.Generator, n: int) -> np.ndarray:
    kind = rng.integers(3)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.arange(len(spectrum)) + 1
    spectrum = spectrum / (freqs ** (0.5 * kind))
    noise = np.fft.irfft(spectrum, n)
    return noise / (np.abs(noise).max() + 1e-9)


def room_impulse(rng: np.random.Generator) -> np.ndarray:
    rt60 = rng.uniform(0.15, 0.7)
    n = int(rt60 * RATE)
    t = np.arange(n) / RATE
    tail = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)
    tail[0] = 1.0
    return tail / np.abs(tail).sum() * rng.uniform(4, 10)


def augment(clip: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    audio = clip.astype(np.float32) / 32768
    speed = rng.uniform(0.86, 1.14)
    audio = resample(audio, max(160, int(len(audio) / speed)))
    if rng.random() < 0.5:
        audio = fftconvolve(audio, room_impulse(rng))[:len(audio) + RATE // 4]
    peak = np.abs(audio).max() + 1e-9
    return audio / peak * 10 ** (rng.uniform(-22, -2) / 20)


def mix_background(
    rng: np.random.Generator,
    length: int,
    babble: list[np.ndarray],
    level_db: tuple[float, float],
) -> np.ndarray:
    out = colored_noise(rng, length) * 10 ** (rng.uniform(-60, -30) / 20)
    if babble and rng.random() < 0.6:
        voice = babble[rng.integers(len(babble))].astype(np.float32) / 32768
        start = rng.integers(0, max(1, length - len(voice)))
        piece = voice[: length - start]
        out[start:start + len(piece)] += piece / (np.abs(piece).max() + 1e-9) * 10 ** (rng.uniform(*level_db) / 20)
    return out


def place_positive(
    word: np.ndarray,
    rng: np.random.Generator,
    seconds: float,
    babble: list[np.ndarray],
) -> np.ndarray:
    length = int(seconds * RATE)
    end = length - int(rng.uniform(0.02, 0.25) * RATE)
    word = word[-end:]
    start = end - len(word)
    out = mix_background(rng, length, babble, (-40, -14))
    out[start:end] += word
    return to_int16(out)


def to_int16(audio: np.ndarray) -> np.ndarray:
    return (np.clip(audio, -1, 1) * 32767).astype(np.int16)
