import json
import os
import sys
import time
from datetime import datetime

from .events import EVENTS

CLEAR = "\x1b[H\x1b[J"
BOLD, DIM, RED, GREEN, YELLOW, CYAN, RESET = "\x1b[1m", "\x1b[2m", "\x1b[31m", "\x1b[32m", "\x1b[33m", "\x1b[36m", "\x1b[0m"
SHOWN = 16


def bar(value: float, full: float = 3000.0, width: int = 30) -> str:
    filled = min(width, int(width * value / full))
    color = GREEN if value < full * 0.5 else YELLOW if value < full * 0.8 else RED
    return f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"


def stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def describe(event: dict) -> str:
    kind = event["kind"]
    if kind == "wake":
        return f"{CYAN}срабатывание{RESET} «{event['key']}» {'сильное' if event['strong'] else 'слабое'}"
    if kind == "rejected":
        return f"{RED}отклонено{RESET} на {event['stage']}: Whisper «{event.get('whisper', '')}» Giga «{event.get('giga', '')}» ({event['secs']} с)"
    if kind == "accepted":
        return f"{GREEN}ПРИНЯТО{RESET} «{event['whisper']}» → команда «{event['command']}»"
    if kind == "turn":
        return f"{GREEN}ответ{RESET} «{event['command']}» → «{event['answer']}»"
    if kind == "busy":
        state["deaf"] += event["secs"]
        return
    if kind == "session":
        return f"{BOLD}старт{RESET} {event.get('mode', '')}"
    return kind


def render(state: dict) -> str:
    now = time.time()
    level = state["level"]
    lines = [
        f"{BOLD}Боб · монитор{RESET}   {DIM}{EVENTS}{RESET}",
        f"сессия {int(now - state['start']) // 60} мин {int(now - state['start']) % 60:02d} с    режим: {state['mode']}",
        "",
        f"микрофон  {bar(level['rms'], 600)}  rms {level['rms']:.0f}  пик {level['peak']}" + (f"  {RED}нет сигнала{RESET}" if now - level["at"] > 10 else ""),
        "",
        f"{YELLOW}глухое время{RESET} {state['deaf']:.0f} с из {max(now - state['start'], 1):.0f} с ({100 * state['deaf'] / max(now - state['start'], 1):.0f}%): пока Боб разбирает срабатывание, он не слышит новое слово",
        "",
        f"срабатываний {BOLD}{state['wake']}{RESET}  (сильных {state['strong']}, слабых {state['wake'] - state['strong']})   "
        f"{RED}отклонено {state['rejected']}{RESET} (Giga {state['by_giga']}, Whisper {state['by_whisper']})   {GREEN}принято {state['accepted']}{RESET}   ответов {state['turns']}",
        "",
        f"{BOLD}последние события{RESET}",
        *[f"{DIM}{stamp(event['ts'])}{RESET} {describe(event)}" for event in state["recent"]],
    ]
    return CLEAR + "\n".join(lines) + "\n"


def apply(state: dict, event: dict) -> None:
    kind = event["kind"]
    if kind == "level":
        state["level"] = {"rms": event["rms"], "peak": event["peak"], "at": event["ts"]}
        return
    if kind == "session":
        state.update(start=event["ts"], mode=event.get("mode", ""), wake=0, strong=0, rejected=0, by_giga=0, by_whisper=0, accepted=0, turns=0, deaf=0.0, recent=[])
    state["wake"] += kind == "wake"
    state["strong"] += kind == "wake" and event["strong"]
    state["rejected"] += kind == "rejected"
    state["by_giga"] += kind == "rejected" and event["stage"] == "gigaam"
    state["by_whisper"] += kind == "rejected" and event["stage"] == "whisper"
    state["accepted"] += kind == "accepted"
    state["turns"] += kind == "turn"
    state["recent"] = [*state["recent"], event][-SHOWN:]


def run_monitor() -> None:
    state = {"start": time.time(), "mode": "—", "wake": 0, "strong": 0, "rejected": 0, "by_giga": 0, "by_whisper": 0, "accepted": 0, "turns": 0, "deaf": 0.0, "recent": [], "level": {"rms": 0.0, "peak": 0, "at": 0.0}}
    while not EVENTS.exists():
        sys.stdout.write(CLEAR + "Жду журнал событий…\n")
        sys.stdout.flush()
        time.sleep(1)
    with EVENTS.open(encoding="utf-8") as file:
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(max(0, size - 400_000))
        for line in file.read().splitlines()[1:]:
            apply(state, json.loads(line))
        while True:
            for line in file.readlines():
                if line.endswith("\n"):
                    apply(state, json.loads(line))
            sys.stdout.write(render(state))
            sys.stdout.flush()
            time.sleep(1)
