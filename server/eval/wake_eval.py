"""Сравнение детекторов кодового слова на сохранённых фразах (запуск из server/: uv run python eval/wake_eval.py). Положительные примеры определяются по тексту Whisper, поэтому метки приблизительные."""
import json, re, sys, wave, copy, os, itertools
import numpy as np
from vosk import SetLogLevel
SetLogLevel(-1)
from bob.config import load_config
from bob.wake import make_wake, normalize
DECOYS = load_config()['wake']['decoys']
cfg = load_config(); UTT = "data/utterances"
rows = [json.loads(l) for l in open(f"{UTT}/index.jsonl", encoding="utf-8")]
giga = json.load(open("eval/giga_texts.json"))["texts"]
POS = re.compile(r"боб|миньон|подручн|сбер|поп\b", re.I)
KEY = re.compile(r"(?<![а-я])(боб\w*|минь?он\w*|подручн\w*|(?:о?кей|ок)\s+сбер\w*)(?![а-я])")
GK = re.compile(r"\bбоб|миньон|подручн|\bсбер|\bпоп\b|\bбоп\b", re.I)
def audio(f):
    with wave.open(f"{UTT}/{f}") as w: return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
c2 = copy.deepcopy(cfg["wake"]); c2["grammar"] = list(dict.fromkeys([*c2["grammar"], *DECOYS]))
wg, wd = make_wake(cfg["wake"], 16000), make_wake(c2, 16000)
flags = {k: [] for k in "GDLV"}; y = []
for r in rows:
    x = audio(r["file"]); y.append(bool(POS.search(r["text"])))
    wg.reset(); wd.reset(); live = wg.live(); g = d = l = False
    for i in range(0, len(x) - 1280, 1280):
        b = x[i:i+1280]
        g |= bool(wg.feed(b)); d |= bool(wd.feed(b)); l |= bool(KEY.search(normalize(live.feed(b))))
    flags["G"].append(g); flags["D"].append(d); flags["L"].append(l); flags["V"].append(bool(GK.search(giga[r["file"]])))
pos = sum(y); neg = len(y) - pos
def score(f):
    tp = sum(1 for a, b in zip(f, y) if a and b); fp = sum(1 for a, b in zip(f, y) if a and not b)
    return tp, fp
combos = {
 "G (как сейчас)": lambda g,d,l,v: g,
 "D (ловушки)": lambda g,d,l,v: d,
 "L (полный Vosk)": lambda g,d,l,v: l,
 "G и (L или V)": lambda g,d,l,v: g and (l or v),
 "D или (G и L)": lambda g,d,l,v: d or (g and l),
 "D или (G и V)": lambda g,d,l,v: d or (g and v),
 "D или (G и (L или V))": lambda g,d,l,v: d or (g and (l or v)),
 "L или V": lambda g,d,l,v: l or v,
 "G и D": lambda g,d,l,v: g and d,
}
print(f"записей {len(y)}: с кодовым словом {pos}, без {neg}")
for name, fn in combos.items():
    f = [fn(*t) for t in zip(*(flags[k] for k in "GDLV"))]
    tp, fp = score(f)
    print(f"{name:26} найдено {tp:2}/{pos}  ({100*tp//pos}%)   ложных {fp:2}/{neg}  ({100*fp//neg}%)")
