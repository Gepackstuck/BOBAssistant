"""Расшифровка всех сохранённых фраз GigaAM (запускать окружением helpers/gigaam): .venv/bin/python eval/giga_texts.py > eval/giga_texts.json"""
import json, sys, wave, re, time
import numpy as np, torch
from transformers import AutoModel
def load(path, *_):
    with wave.open(path) as f:
        return torch.from_numpy(np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768)
model = AutoModel.from_pretrained("ai-sage/GigaAM-v3", revision="rnnt", trust_remote_code=True)
for m in list(sys.modules.values()):
    if getattr(m, "__name__", "").endswith("modeling_gigaam") and hasattr(m, "load_audio"):
        m.load_audio = load
import pathlib
UTT = str(pathlib.Path(__file__).resolve().parent.parent / "data" / "utterances")
rows = [json.loads(l) for l in open(f"{UTT}/index.jsonl", encoding="utf-8")]
out = {}
t = time.time()
for r in rows:
    out[r["file"]] = model.transcribe(f"{UTT}/{r['file']}")
print(json.dumps({"seconds": time.time() - t, "texts": out}, ensure_ascii=False))
