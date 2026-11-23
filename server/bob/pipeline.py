import itertools
import json
import re
import threading
import time
import wave
from datetime import datetime

import numpy as np

from .config import ROOT
from .assistant import DETAIL_MARK
from .devices import Device
from .events import emit
from .listen import Vad, capture, looks_unfinished
from .music import phonetic_hint
from .wake import GIGA_WAKE_RE, make_wake, remove_wake, sounds_like_wake, strip_wake

PLATE_INTERVAL = 0.12
PLAY_RE = re.compile(r"^\s*(?:боб[\s,.!]+)?(?:включи|поставь|сыграй|запусти|найди|давай)\b", re.IGNORECASE)
UTTERANCES = ROOT / "data" / "utterances"
TRIGGERS = ROOT / "data" / "triggers"
RECORDINGS = ROOT / "data" / "recordings"


class Stopwatch:
    def __init__(self):
        self.marks: list[tuple[str, float]] = []
        self.last = time.perf_counter()

    def lap(self, name: str) -> None:
        current = time.perf_counter()
        self.marks.append((name, current - self.last))
        self.last = current

    def line(self) -> str:
        total = sum(seconds for _, seconds in self.marks)
        return " | ".join(f"{name} {seconds:.2f} с" for name, seconds in self.marks) + f" | итого {total:.2f} с"


def scaled(chunks, volume: int):
    gain = (volume / 100) ** 2
    return chunks if gain >= 1 else (chunk * gain for chunk in chunks)


def reading_seconds(text: str) -> float:
    return max(4.0, 2.0 + 0.06 * len(text))


class Brain:
    def __init__(self, cfg: dict, assistant, whisper, tts, settings):
        self.cfg = cfg
        self.assistant = assistant
        self.whisper = whisper
        self.tts = tts
        self.settings = settings
        self.stt_lock = threading.Lock()
        self.turn_lock = threading.Lock()
        self.claim_lock = threading.Lock()
        self.claimed_by: str | None = None
        self.claimed_at = 0.0
        self.phonetic = None

    def transcribe(self, audio):
        with self.stt_lock:
            return self.whisper.transcribe(audio)

    def claim(self, device: str) -> bool:
        with self.claim_lock:
            now = time.monotonic()
            if self.claimed_by and self.claimed_by != device and now - self.claimed_at < 2.0:
                return False
            self.claimed_by, self.claimed_at = device, now
            return True


class Listener(threading.Thread):
    def __init__(self, device: Device, brain: Brain, observe: bool = False):
        super().__init__(daemon=True, name=f"listener-{device.name}")
        self.device = device
        self.brain = brain
        self.observe = observe
        cfg = brain.cfg
        self.wake = make_wake(cfg["wake"], device.sample_rate)
        self.vad = Vad(cfg["listen"]["speech_threshold"])
        self.listen_cfg = cfg["listen"]
        self.log_text = cfg["debug"]["log_text"]
        self.verify = cfg["wake"].get("verify_with_stt", True)
        self.held = False
        self.visible = False
        self.heard_audio = None
        self.rewoken: str | None = None
        self.record = True

    def log(self, message: str) -> None:
        print(f"[{self.device.name}] {message}", flush=True)

    def transcribe(self, audio) -> str:
        self.heard_audio = audio
        text = self.brain.transcribe(audio)
        keep = self.brain.cfg["debug"].get("keep_utterances", 0)
        if keep and self.device.name == "mac" and audio.size:
            self.save_utterance(audio, text, keep)
        return text

    def phonetic_check(self, audio) -> tuple[bool | None, str]:
        phonetic = self.brain.phonetic
        if phonetic is None or not phonetic.available:
            return None, ""
        text = phonetic.transcribe(audio)
        return sounds_like_wake(text), text

    def barge_monitor(self, block):
        key = self.wake.feed(block)
        return key if key and self.wake.strong else None

    def save_trigger(self, audio, key: str, strong: bool, live: bool, giga: str, heard: str, accepted: bool) -> None:
        keep = self.brain.cfg["debug"].get("keep_triggers", 0)
        if not keep or audio is None or audio.size == 0:
            return
        TRIGGERS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        name = f"{self.device.name}-{stamp}.wav"
        with wave.open(str(TRIGGERS / name), "wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(self.device.sample_rate)
            file.writeframes(audio.astype("int16").tobytes())
        entry = {"file": name, "device": self.device.name, "key": key, "strong": strong, "live": live, "giga": giga, "whisper": heard, "accepted": accepted}
        with (TRIGGERS / "index.jsonl").open("a", encoding="utf-8") as index:
            index.write(json.dumps(entry, ensure_ascii=False) + "\n")
        for old in sorted(TRIGGERS.glob("*.wav"))[:-keep]:
            old.unlink()

    def save_utterance(self, audio, text: str, keep: int) -> None:
        UTTERANCES.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        with wave.open(str(UTTERANCES / f"{stamp}.wav"), "wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(self.device.sample_rate)
            file.writeframes(audio.astype("int16").tobytes())
        with (UTTERANCES / "index.jsonl").open("a", encoding="utf-8") as index:
            index.write(json.dumps({"file": f"{stamp}.wav", "text": text}, ensure_ascii=False) + "\n")
        for old in sorted(UTTERANCES.glob("*.wav"))[:-keep]:
            old.unlink()

    @property
    def voice(self) -> bool:
        return self.brain.settings.voice(self.device.name)

    def show(self, phase: str, request: str = "", answer: str = "", window: float = 0) -> None:
        if self.observe:
            return
        self.visible = phase != "idle"
        self.device.plate(phase, request, answer, self.voice, self.brain.settings.theme(self.device.name), window)

    def hold(self, value: bool) -> None:
        if self.observe:
            return
        if value != self.held:
            self.held = value
            self.device.media(value)
            self.brain.assistant.music.duck(self.device.name, value)

    def open_recording(self):
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        file = wave.open(str(RECORDINGS / f"{self.device.name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.wav"), "wb")
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(self.device.sample_rate)
        return file

    def tap(self, recording):
        read = self.device.read
        level = {"at": 0.0}

        def tapped(timeout=None):
            block = read(timeout)
            if block is not None:
                recording.writeframes(block.astype("int16").tobytes())
                now = time.monotonic()
                if now - level["at"] >= 2.0:
                    level["at"] = now
                    emit("level", device=self.device.name, rms=round(float(getattr(self.device, "rms", 0.0)), 1), peak=int(getattr(self.device, "peak", 0)), clean=round(float(np.sqrt(np.mean(block.astype(np.float32) ** 2))), 1), helper=bool(getattr(self.device, "helper_active", False)))
            return block

        self.device.read = tapped
        if hasattr(self.device, "raw_sink"):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            raw_mic = wave.open(str(RECORDINGS / f"{self.device.name}-raw-mic-{stamp}.wav"), "wb")
            raw_mic.setnchannels(1)
            raw_mic.setsampwidth(2)
            raw_mic.setframerate(self.device.sample_rate)
            raw_ref = (RECORDINGS / f"{self.device.name}-raw-ref-{stamp}.f32").open("wb")
            self.device.raw_sink = lambda mic, ref: (raw_mic.writeframes(mic.tobytes()), raw_ref.write(ref.tobytes()))

    def run(self) -> None:
        silent_blocks = 0
        recording = self.open_recording() if self.observe and self.record else None
        if recording is not None:
            self.tap(recording)
        while self.device.alive:
            block = self.device.read(timeout=1)
            if block is None:
                continue
            if silent_blocks >= 0:
                silent_blocks = silent_blocks + 1 if not block.any() else -1
                if silent_blocks == 40:
                    self.log("⚠️ Микрофон отдаёт тишину: нет доступа к микрофону.")
                    silent_blocks = -1
            key = self.wake.feed(block)
            while key:
                busy_since = time.monotonic()
                position = getattr(self.device, "position", None)
                try:
                    key = self.handle(key)
                except Exception as error:
                    self.log(f"ошибка: {error}")
                    key = None
                finally:
                    emit("busy", device=self.device.name, secs=round(time.monotonic() - busy_since, 1), audio=round((self.device.position - position) / self.device.sample_rate, 1) if position is not None else None)
                    if not key:
                        self.hold(False)
                        if self.visible:
                            self.show("idle")
                    self.wake.reset()
        if recording is not None:
            recording.close()
        self.log("отключено")

    def listen_live(self, preroll, start_timeout=None, require_wake=False, min_speech=0.0, rewake=False):
        live = self.wake.live()
        shown = {"on": False, "text": None, "at": 0.0, "latest": "", "replayed": 0}
        self.rewoken = None

        def on_block(block):
            if rewake and shown["replayed"] >= len(preroll):
                key = self.wake.feed(block)
                if key and self.wake.strong:
                    self.rewoken = key
            shown["replayed"] += 1
            text = live.feed(block)
            if require_wake:
                matched, text = strip_wake(text) if text else (False, "")
                if not matched:
                    return
            elif not text:
                return
            shown["latest"] = text
            if not shown["on"]:
                shown["on"] = True
                self.hold(True)
            now = time.monotonic()
            if text != shown["text"] and now - shown["at"] >= PLATE_INTERVAL:
                shown["text"], shown["at"] = text, now
                self.show("listening", text)

        audio, voiced = capture(self.device, self.vad, self.listen_cfg, preroll, start_timeout, on_block, min_speech, lambda: looks_unfinished(shown["latest"]), lambda: self.rewoken is not None)
        return audio, voiced, shown["on"], shown["latest"]

    def handle(self, key: str) -> str | None:
        if not self.brain.claim(self.device.name):
            self.log(f"«{key}» услышало другое устройство")
            self.device.drain()
            return None
        strong = self.wake.strong
        self.log(f"🎙 «{key}», слушаю" + ("" if strong else " (слабое срабатывание)"))
        emit("wake", device=self.device.name, key=key, strong=strong)
        if strong:
            self.show("listening")
        preroll = self.device.take_preroll()
        giga_text = ""
        quick_ok = False
        if not strong and preroll:
            verdict, giga_text = self.phonetic_check(np.concatenate(preroll))
            if verdict is False:
                self.log(f"ложное срабатывание (быстрая проверка, GigaAM: «{giga_text}»)" if self.log_text else "ложное срабатывание (быстрая проверка)")
                emit("rejected", device=self.device.name, key=key, stage="gigaam-fast", giga=giga_text, secs=round(sum(len(block) for block in preroll) / self.device.sample_rate, 1))
                return None
            quick_ok = bool(GIGA_WAKE_RE.search(giga_text))
        self.wake.reset()
        audio, voiced, confirmed, live_text = self.listen_live(preroll, require_wake=True, rewake=True)
        if self.rewoken:
            again, self.rewoken = self.rewoken, None
            emit("rearmed", device=self.device.name, key=again)
            self.log(f"«{again}» услышано во время прослушивания, начинаю заново")
            return again
        confirmed = confirmed or quick_ok
        if not strong and not confirmed:
            verdict, giga_text = self.phonetic_check(audio)
            if verdict is False:
                self.log(f"ложное срабатывание (слабое, GigaAM: «{giga_text}»)" if self.log_text else "ложное срабатывание (слабое)")
                emit("rejected", device=self.device.name, key=key, stage="gigaam", giga=giga_text, secs=round(len(audio) / self.device.sample_rate, 1))
                self.save_trigger(audio, key, strong, confirmed, giga_text, "", False)
                return None
            confirmed = bool(GIGA_WAKE_RE.search(giga_text))
        watch = Stopwatch()
        heard = self.transcribe(audio) if voiced else ""
        watch.lap("речь→текст")
        if self.log_text:
            self.log(f"whisper: «{heard}» vosk: «{live_text}» ({len(audio) / self.device.sample_rate:.1f} с)")
        verified, command = strip_wake(heard)
        if self.verify and not verified and not confirmed:
            self.log(f"ложное срабатывание: «{heard}»" if self.log_text else "ложное срабатывание")
            emit("rejected", device=self.device.name, key=key, stage="whisper", giga=giga_text, whisper=heard, vosk=live_text, secs=round(len(audio) / self.device.sample_rate, 1))
            self.save_trigger(audio, key, strong, confirmed, giga_text, heard, False)
            return None
        self.save_trigger(audio, key, strong, confirmed, giga_text, heard, True)
        if not verified:
            command = self.after_wake(heard, live_text) if confirmed else remove_wake(heard)
        emit("accepted", device=self.device.name, key=key, strong=strong, giga=giga_text, whisper=heard, vosk=live_text, command=command, secs=round(len(audio) / self.device.sample_rate, 1), stt_secs=round(watch.marks[0][1], 2) if watch.marks else None)
        if self.observe:
            return None
        self.hold(True)
        if not command:
            self.show("listening")
            if self.voice:
                self.device.chime()
            audio, voiced, confirmed, live_text = self.listen_live([])
            watch = Stopwatch()
            command = remove_wake(self.transcribe(audio)) if voiced else ""
            watch.lap("речь→текст")
        if not command:
            self.log("не услышал команду")
            return None
        return self.converse(key, command, watch)

    def after_wake(self, heard: str, live_text: str) -> str:
        count = len(live_text.split())
        words = heard.split()
        return " ".join(words[-count:]) if 0 < count < len(words) else remove_wake(heard)

    def converse(self, key: str, command: str, watch: Stopwatch) -> str | None:
        brain = self.brain
        device = self.device
        turns = 0
        started = time.monotonic()
        while command:
            self.log(f"Вы: {command}")
            self.show("thinking", command)
            hint = brain.phonetic.transcribe(self.heard_audio) if brain.phonetic and PLAY_RE.search(command) and self.heard_audio is not None else ""
            if hint:
                self.log(f"по звучанию: «{hint}»")
            token = phonetic_hint.set(hint)
            try:
                with brain.turn_lock:
                    answer = brain.assistant.handle(command, device.name)
            finally:
                phonetic_hint.reset(token)
            watch.lap("модель")
            spoken, _, extra = answer.partition(DETAIL_MARK)
            spoken = spoken.strip()
            shown = f"{spoken} {extra.strip()}".strip()
            self.log(f"Боб: {spoken or '(молча)'}" + (f" ‖ на плашке: {extra.strip()}" if extra.strip() else ""))
            emit("turn", device=device.name, command=command, answer=spoken, model_secs=round(watch.marks[-1][1], 2) if watch.marks else None)
            if not answer:
                break
            voice = self.voice
            self.show("answer", command, shown)
            window = self.listen_cfg["followup_seconds"]
            if voice:
                chunks = scaled(brain.tts.stream(spoken, brain.tts.voice_for(key)), brain.settings.volume(device.name))
                first = next(chunks, None)
                watch.lap("синтез")
                self.log(f"⏱ {watch.line()}")
                if first is not None:
                    self.wake.reset()
                    barged = device.play(itertools.chain([first], chunks), brain.tts.sample_rate, self.barge_monitor if self.listen_cfg.get("barge_in") else None)
                    if barged:
                        self.log("↪ перебил")
                        return barged
            else:
                self.log(f"⏱ {watch.line()}")
                window = max(window, reading_seconds(shown))
            turns += 1
            if turns > self.listen_cfg["max_followups"] or time.monotonic() - started > self.listen_cfg["conversation_seconds"]:
                time.sleep(min(reading_seconds(shown), 6.0) if not voice else 1.5)
                break
            self.show("followup", command, shown, window)
            audio, voiced, confirmed, live_text = self.listen_live([], start_timeout=window, min_speech=self.listen_cfg["followup_min_speech"])
            watch = Stopwatch()
            command = remove_wake(self.transcribe(audio)) if voiced else ""
            watch.lap("речь→текст")
            if command:
                self.log("↪ уточнение")
