import json
import sys

import numpy as np
import torch
from torch import nn

from common import DATA, ROOT, load_clips, load_words
from features import FEATURES, embedder

MODELS = ROOT / "models" / "trained"


class WakeNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(16 * 96, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def logits(self, x):
        return self.net(x).squeeze(-1)

    def forward(self, x):
        return torch.sigmoid(self.net(x))


def load(name: str) -> np.ndarray:
    return np.load(FEATURES / f"{name}.npy")


def dataset(word: str, words: list[str], part: str) -> tuple[np.ndarray, np.ndarray]:
    positive = np.concatenate([load(f"pos_{word}_{part}"), *([load(f"posrand_{word}_train")] if part == "train" else [])])
    negative = np.concatenate([
        load(f"speech_{part}"),
        load(f"stream_{part}"),
        load(f"hard_{word}_{part}"),
        load("noise"),
        *[load(f"pos_{other}_{part}") for other in words if other != word],
        *[load(f"hard_{other}_{part}") for other in words if other != word],
    ])
    x = np.concatenate([positive, negative])
    y = np.concatenate([np.ones(len(positive)), np.zeros(len(negative))]).astype(np.float32)
    return x, y


def fit(x: np.ndarray, y: np.ndarray, vx: np.ndarray, vy: np.ndarray, epochs: int = 30) -> WakeNet:
    torch.manual_seed(3)
    model = WakeNet()
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-2)
    xs, ys = torch.from_numpy(x), torch.from_numpy(y)
    vxs, vys = torch.from_numpy(vx), torch.from_numpy(vy)
    pos_weight = float((ys == 0).sum() / max(1, (ys == 1).sum())) ** 0.5
    best, best_state = None, None
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(xs))
        for i in range(0, len(xs), 512):
            idx = order[i:i + 512]
            target = ys[idx] * 0.95 + 0.025
            loss = nn.functional.binary_cross_entropy_with_logits(
                model.logits(xs[idx]), target, pos_weight=torch.tensor(pos_weight)
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val = nn.functional.binary_cross_entropy_with_logits(
                model.logits(vxs), vys, pos_weight=torch.tensor(pos_weight)
            ).item()
        if best is None or val < best:
            best, best_state = val, {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    model.eval()
    return model


def scores(model: WakeNet, x: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        return model(torch.from_numpy(x)).squeeze(1).numpy()


def stream_false_accepts(model: WakeNet, threshold: float, clips: list[np.ndarray]) -> tuple[int, float]:
    gap = np.zeros(8000, np.int16)
    stream = np.concatenate([part for clip in clips for part in (clip, gap)])
    frames = embedder().embed_clips(stream[None, :], batch_size=1)[0]
    windows = np.stack([frames[i - 16:i] for i in range(16, len(frames) + 1)])
    hits = scores(model, windows.astype(np.float32)) >= threshold
    triggers, cooldown = 0, 0
    for hit in hits:
        cooldown -= 1
        if hit and cooldown <= 0:
            triggers, cooldown = triggers + 1, 25
    return triggers, len(stream) / 16000 / 3600


def export(model: WakeNet, word: str) -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model, torch.zeros(1, 16, 96), str(MODELS / f"{word}.onnx"),
        input_names=["features"], output_names=["score"], opset_version=13, dynamo=False,
    )


def main(only: list[str]) -> None:
    cfg = load_words()
    words = list(cfg["words"])
    held = cfg["voices"]["holdout"]
    speech_val = [
        c for c, v in zip(*load_clips(DATA / "clips" / "neg_speech.npz")) if v.split(":")[1] in held
    ]
    report = {}
    for word in words:
        if only and word not in only:
            continue
        x, y = dataset(word, words, "train")
        vx, vy = dataset(word, words, "val")
        model = fit(x, y, vx, vy)
        vs = scores(model, vx)
        stream_scores = np.sort(scores(model, load("stream_val")))
        threshold = float(min(0.99, max(0.5, stream_scores[-3] + 1e-3)))
        recall = float((vs[vy == 1] >= threshold).mean())
        hard = scores(model, load(f"hard_{word}_val"))
        false_accepts, hours = stream_false_accepts(model, threshold, speech_val)
        report[word] = {
            "threshold": round(threshold, 3),
            "recall": round(recall, 3),
            "hard_negative_accepts": round(float((hard >= threshold).mean()), 3),
            "false_accepts_per_hour": round(false_accepts / hours, 2),
            "speech_hours_checked": round(hours, 2),
            "train_positive": int(y.sum()),
            "train_negative": int(len(y) - y.sum()),
        }
        export(model, word)
        print(word, report[word], flush=True)
    path = MODELS / "report.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps({**previous, **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
