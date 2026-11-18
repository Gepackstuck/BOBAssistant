import sys

import numpy as np
from openwakeword.utils import AudioFeatures

from common import (
    DATA, RATE, ROOT, augment, colored_noise, load_clips, load_words, mix_background, place_positive, to_int16,
)

FEATURES = DATA / "features"


def embedder() -> AudioFeatures:
    return AudioFeatures(
        melspec_model_path=str(ROOT / "models" / "oww" / "melspectrogram.onnx"),
        embedding_model_path=str(ROOT / "models" / "oww" / "embedding_model.onnx"),
        inference_framework="onnx",
        ncpu=6,
    )


def split(clips: list[np.ndarray], voices: list[str], holdout: list[str]) -> dict[str, list[np.ndarray]]:
    held = [c for c, v in zip(clips, voices) if v.split(":")[1] in holdout]
    kept = [c for c, v in zip(clips, voices) if v.split(":")[1] not in holdout]
    return {"train": kept, "val": held}


def end_aligned(clips, rng, seconds, babble, copies) -> np.ndarray:
    return np.stack([
        place_positive(augment(clip, rng), rng, seconds, babble)
        for clip in clips
        for _ in range(copies)
    ])


def speech_crops(clips, rng, seconds, babble, copies) -> np.ndarray:
    length = int(seconds * RATE)
    out = []
    for clip in clips:
        for _ in range(copies):
            voice = augment(clip, rng)
            canvas = mix_background(rng, length, babble, (-45, -20))
            shift = rng.integers(-len(voice) + RATE // 4, length - RATE // 4)
            a, b = max(0, shift), min(length, shift + len(voice))
            canvas[a:b] += voice[a - shift:b - shift]
            out.append(to_int16(canvas))
    return np.stack(out)


def stream_windows(features: AudioFeatures, clips, rng, babble, stride: int) -> np.ndarray:
    pieces = []
    for clip in clips:
        pieces.append(augment(clip, rng))
        pieces.append(np.zeros(int(rng.uniform(0.1, 1.0) * RATE), np.float32))
    stream = np.concatenate(pieces)
    windows = []
    chunk = 60 * RATE
    for start in range(0, len(stream), chunk):
        part = stream[max(0, start - 2 * RATE):start + chunk]
        part = part + mix_background(rng, len(part), [], (-60, -40))
        frames = features.embed_clips(to_int16(part)[None, :], batch_size=1)[0]
        windows.extend(frames[i - 16:i] for i in range(16, len(frames) + 1, stride))
    return np.stack(windows).astype(np.float32)


def noise_clips(rng, seconds, count) -> np.ndarray:
    length = int(seconds * RATE)
    return np.stack([
        to_int16(colored_noise(rng, length) * 10 ** (rng.uniform(-50, -10) / 20))
        for _ in range(count)
    ])


def embed(features: AudioFeatures, name: str, audio: np.ndarray) -> None:
    FEATURES.mkdir(parents=True, exist_ok=True)
    vectors = features.embed_clips(audio, batch_size=256, ncpu=6)
    np.save(FEATURES / f"{name}.npy", vectors[:, -16:, :].astype(np.float32))
    print(f"   {name}: {vectors.shape[0]}", flush=True)


def main(only: list[str]) -> None:
    cfg = load_words()
    holdout = cfg["voices"]["holdout"]
    seconds = cfg["samples"]["clip_seconds"]
    copies = cfg["samples"]["augment_per_positive"]
    rng = np.random.default_rng(11)
    features = embedder()
    speech = split(*load_clips(DATA / "clips" / "neg_speech.npz"), holdout)
    for part in ("train", "val"):
        if not (FEATURES / f"speech_{part}.npy").exists():
            embed(features, f"speech_{part}", speech_crops(speech[part], rng, seconds, speech[part], 3))
    for part, stride in (("train", 2), ("val", 1)):
        target = FEATURES / f"stream_{part}.npy"
        if not target.exists():
            np.save(target, stream_windows(features, speech[part], rng, speech[part], stride))
            print(f"   stream_{part}: {len(np.load(target, mmap_mode='r'))}", flush=True)
    if not (FEATURES / "noise.npy").exists():
        embed(features, "noise", noise_clips(rng, seconds, 600))
    for word in cfg["words"]:
        if only and word not in only:
            continue
        positives = split(*load_clips(DATA / "clips" / f"pos_{word}.npz"), holdout)
        hard = split(*load_clips(DATA / "clips" / f"hard_{word}.npz"), holdout)
        random_voices = load_clips(DATA / "clips" / f"posrand_{word}.npz")[0]
        if not (FEATURES / f"posrand_{word}_train.npy").exists():
            embed(features, f"posrand_{word}_train", end_aligned(random_voices, rng, seconds, speech["train"], 2))
        for part in ("train", "val"):
            if not (FEATURES / f"pos_{word}_{part}.npy").exists():
                embed(features, f"pos_{word}_{part}", end_aligned(positives[part], rng, seconds, speech[part], copies))
            if not (FEATURES / f"hard_{word}_{part}.npy").exists():
                embed(features, f"hard_{word}_{part}", end_aligned(hard[part], rng, seconds, speech[part], copies))


if __name__ == "__main__":
    main(sys.argv[1:])
