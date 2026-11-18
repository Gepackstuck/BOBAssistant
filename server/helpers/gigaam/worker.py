import json
import sys
import wave

import numpy as np
import torch
from transformers import AutoModel

REVISION = "rnnt"


def load(path, *_):
    with wave.open(path) as file:
        return torch.from_numpy(np.frombuffer(file.readframes(file.getnframes()), dtype=np.int16).astype(np.float32) / 32768)


def main() -> None:
    model = AutoModel.from_pretrained("ai-sage/GigaAM-v3", revision=REVISION, trust_remote_code=True)
    for module in list(sys.modules.values()):
        if getattr(module, "__name__", "").endswith("modeling_gigaam") and hasattr(module, "load_audio"):
            module.load_audio = load
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        try:
            text = model.transcribe(request["wav"])
        except Exception as error:
            print(json.dumps({"error": str(error)}), flush=True)
            continue
        print(json.dumps({"text": text}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
