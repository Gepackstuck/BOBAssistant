import sys
from pathlib import Path

import numpy as np
import torch
from piper import PiperVoice
from piper.config import SynthesisConfig

from common import DATA, ROOT, load_words, save_clips, to_16k, to_int16, trim_silence

SILERO = ROOT.parent / "server" / "models" / "silero" / "v4_ru.pt"


class Voices:
    def __init__(self, cfg: dict, rng: np.random.Generator):
        torch.set_num_threads(6)
        self.silero = torch.package.PackageImporter(str(SILERO)).load_pickle("tts_models", "model")
        self.piper = {
            name: PiperVoice.load(str(ROOT / "models" / "piper" / f"ru_RU-{name}-medium.onnx"))
            for name in cfg["voices"]["piper"]
        }
        self.names = [f"silero:{s}" for s in cfg["voices"]["silero_speakers"]] + [f"piper:{p}" for p in self.piper]
        self.rng = rng

    def say(self, text: str, voice: str) -> np.ndarray | None:
        engine, name = voice.split(":")
        try:
            if engine == "silero":
                audio = self.silero.apply_tts(
                    text=text, speaker=name, sample_rate=24000, put_accent=True, put_yo=True
                ).numpy()
                return trim_silence(to_16k(audio, 24000))
            config = SynthesisConfig(
                length_scale=float(self.rng.uniform(0.8, 1.3)),
                noise_scale=float(self.rng.uniform(0.4, 0.9)),
                noise_w_scale=float(self.rng.uniform(0.5, 1.0)),
            )
            plain = text.replace("+", "")
            chunks = list(self.piper[name].synthesize(plain, syn_config=config))
            rate = chunks[0].sample_rate
            audio = np.concatenate([c.audio_float_array for c in chunks])
            return trim_silence(to_16k(audio, rate))
        except Exception as error:
            print(f"   {voice} «{text}»: {error}", flush=True)
            return None

    def batch(self, texts: list[str], count: int, label: str, only_voice: str | None = None) -> tuple[list[np.ndarray], list[str]]:
        clips, voices = [], []
        while len(clips) < count:
            voice = only_voice or self.names[len(clips) % len(self.names)]
            text = texts[self.rng.integers(len(texts))]
            audio = self.say(text, voice)
            if audio is not None and len(audio) > 1600:
                clips.append(to_int16(audio / (np.abs(audio).max() + 1e-9) * 0.9))
                voices.append(voice)
            if len(clips) % 200 == 0 and clips:
                print(f"   {label}: {len(clips)}/{count}", flush=True)
        return clips, voices


def main(only: list[str]) -> None:
    cfg = load_words()
    rng = np.random.default_rng(7)
    voices = Voices(cfg, rng)
    samples = cfg["samples"]
    for word, spec in cfg["words"].items():
        if only and word not in only:
            continue
        target = DATA / "clips" / f"pos_{word}.npz"
        if not target.exists():
            print(f"{word}: позитивы", flush=True)
            save_clips(target, *voices.batch(spec["phrases"], samples["positive_per_word"], word))
        target = DATA / "clips" / f"posrand_{word}.npz"
        if not target.exists():
            print(f"{word}: случайные голоса", flush=True)
            save_clips(target, *voices.batch(spec["phrases"], samples["random_positive_per_word"], word, "silero:random"))
        target = DATA / "clips" / f"hard_{word}.npz"
        if not target.exists():
            print(f"{word}: похожие слова", flush=True)
            save_clips(target, *voices.batch(spec["hard_negatives"], samples["hard_negative_per_word"], word))
    target = DATA / "clips" / "neg_speech.npz"
    texts_path = DATA / "negative_texts.txt"
    if (not only or "speech" in only) and not target.exists() and texts_path.exists():
        texts = [t for t in texts_path.read_text(encoding="utf-8").splitlines() if t.strip()]
        print(f"речь: {len(texts)} фраз", flush=True)
        save_clips(target, *voices.batch(texts, samples["negative_sentences"], "речь"))


if __name__ == "__main__":
    main(sys.argv[1:])
