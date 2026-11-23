import json
import threading
import time

from .config import ROOT

EVENTS = ROOT / "data" / "events.jsonl"
lock = threading.Lock()


def emit(kind: str, **fields) -> None:
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": round(time.time(), 3), "kind": kind, **fields}, ensure_ascii=False)
    with lock:
        with EVENTS.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
