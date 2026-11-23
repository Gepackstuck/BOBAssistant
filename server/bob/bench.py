import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import torch
from silero_vad import get_speech_timestamps, load_silero_vad

from .config import ROOT

RATE = 16000
MAX_SEGMENT = 25.0
GAP = 0.6
MIN_SEGMENT = 0.4
JARVIS_RE = re.compile(r"жарв|жерв|ярвис", re.IGNORECASE)
WHISPER_MODELS = {
    "whisper-large-v3": "mlx-community/whisper-large-v3-mlx",
    "whisper-turbo": "mlx-community/whisper-large-v3-turbo",
}


def load_wav(path: Path) -> np.ndarray:
    data = path.read_bytes()[44:]
    return np.frombuffer(data[: len(data) // 2 * 2], dtype=np.int16)


def segments(audio: np.ndarray) -> list[tuple[int, int]]:
    stamps = get_speech_timestamps(
        torch.from_numpy(audio.astype(np.float32) / 32768), load_silero_vad(onnx=True), sampling_rate=RATE,
        min_silence_duration_ms=int(GAP * 1000), min_speech_duration_ms=int(MIN_SEGMENT * 1000), speech_pad_ms=200,
    )
    return [(item["start"], item["end"]) for item in stamps]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower().replace("ё", "е"))).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio() if a or b else 1.0


def whisper_runner(repo: str):
    import mlx_whisper

    def run(audio: np.ndarray) -> str:
        result = mlx_whisper.transcribe(audio.astype(np.float32) / 32768, path_or_hf_repo=repo, language="ru", condition_on_previous_text=False, no_speech_threshold=0.6)
        return result.get("text", "").strip()

    run(np.zeros(RATE, dtype=np.int16))
    return run


def gigaam_runner():
    from .phonetic import Phonetic
    phonetic = Phonetic()
    phonetic.start()
    while not phonetic.available:
        time.sleep(0.5)
    return phonetic.transcribe


def runners(names: list[str]) -> dict:
    return {name: (gigaam_runner if name == "gigaam" else (lambda repo=WHISPER_MODELS[name]: whisper_runner(repo)))() for name in names}


def run_bench(path: str, names: list[str], limit_minutes: float | None) -> None:
    audio = load_wav(Path(path))
    if limit_minutes:
        audio = audio[: int(limit_minutes * 60 * RATE)]
    spans = segments(audio)
    total_speech = sum(end - start for start, end in spans) / RATE
    print(f"запись {len(audio) / RATE / 60:.1f} мин, речи {total_speech / 60:.1f} мин, фрагментов {len(spans)}", flush=True)
    models = runners(names)
    rows = [{"start": round(start / RATE, 1), "secs": round((end - start) / RATE, 1), "text": {}, "time": {}} for start, end in spans]
    for name, run in models.items():
        for row, (start, end) in zip(rows, spans):
            began = time.perf_counter()
            row["text"][name] = run(audio[start:end])
            row["time"][name] = round(time.perf_counter() - began, 2)
        print(f"{name}: готово", flush=True)
    out = ROOT / "data" / "bench"
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(path).stem
    (out / f"{stem}.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    (out / f"{stem}.md").write_text(report(stem, rows, names, len(audio) / RATE, total_speech), encoding="utf-8")
    print(f"отчёт: {out / (stem + '.md')}")


def report(stem: str, rows: list[dict], names: list[str], total: float, speech: float) -> str:
    lines = [f"# Сравнение распознавания: {stem}", "", f"Запись {total / 60:.1f} мин, речи {speech / 60:.1f} мин, фрагментов {len(rows)}.", "", "| модель | время / речь | слов | «джарвис» в тексте |", "|---|---|---|---|"]
    for name in names:
        seconds = sum(row["time"][name] for row in rows)
        words = sum(len(row["text"][name].split()) for row in rows)
        marks = sum(1 for row in rows if JARVIS_RE.search(row["text"][name]))
        lines.append(f"| {name} | {seconds / max(speech, 1):.2f}× | {words} | {marks} |")
    if len(names) > 1:
        lines += ["", "Сходство текстов моделей (1.0 — одинаково):", "", "| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for a in names:
            lines.append(f"| {a} | " + " | ".join(f"{np.mean([similarity(row['text'][a], row['text'][b]) for row in rows]):.2f}" for b in names) + " |")
    lines += ["", "## Фрагменты (где модели расходятся сильнее всего — сверху)", ""]
    spread = lambda row: min((similarity(row["text"][a], row["text"][b]) for a in names for b in names), default=1.0)
    for row in sorted(rows, key=spread)[:40]:
        lines.append(f"**{row['start']} с, {row['secs']} с**")
        lines += [f"- {name}: {row['text'][name] or '—'}" for name in names]
        lines.append("")
    return "\n".join(lines)
