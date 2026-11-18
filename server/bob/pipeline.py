import itertools
import json
import threading
import time
import wave
from datetime import datetime

from .config import ROOT
from .devices import Device
from .listen import Vad, capture, looks_unfinished
from .wake import make_wake, remove_wake, strip_wake

PLATE_INTERVAL = 0.12
UTTERANCES = ROOT / "data" / "utterances"


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
    def __init__(self, device: Device, brain: Brain):
        super().__init__(daemon=True, name=f"listener-{device.name}")
        self.device = device
        self.brain = brain
        cfg = brain.cfg
        self.wake = make_wake(cfg["wake"], device.sample_rate)
        self.vad = Vad(cfg["listen"]["speech_threshold"])
        self.listen_cfg = cfg["listen"]
        self.log_text = cfg["debug"]["log_text"]
        self.verify = cfg["wake"].get("verify_with_stt", True)
        self.held = False
        self.visible = False

    def log(self, message: str) -> None:
        print(f"[{self.device.name}] {message}", flush=True)

    def transcribe(self, audio) -> str:
        text = self.brain.transcribe(audio)
        keep = self.brain.cfg["debug"].get("keep_utterances", 0)
        if keep and self.device.name == "mac" and audio.size:
            self.save_utterance(audio, text, keep)
        return text

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
        self.visible = phase != "idle"
        self.device.plate(phase, request, answer, self.voice, self.brain.settings.theme(self.device.name), window)

    def hold(self, value: bool) -> None:
        if value != self.held:
            self.held = value
            self.device.media(value)
            self.brain.assistant.music.duck(self.device.name, value)

    def run(self) -> None:
        silent_blocks = 0
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
                try:
                    key = self.handle(key)
                except Exception as error:
                    self.log(f"ошибка: {error}")
                    key = None
                finally:
                    if not key:
                        self.hold(False)
                        if self.visible:
                            self.show("idle")
                    self.wake.reset()
        self.log("отключено")

    def listen_live(self, preroll, start_timeout=None, require_wake=False, min_speech=0.0):
        live = self.wake.live()
        shown = {"on": False, "text": None, "at": 0.0, "latest": ""}

        def on_block(block):
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

        audio, voiced = capture(self.device, self.vad, self.listen_cfg, preroll, start_timeout, on_block, min_speech, lambda: looks_unfinished(shown["latest"]))
        return audio, voiced, shown["on"], shown["latest"]

    def handle(self, key: str) -> str | None:
        if not self.brain.claim(self.device.name):
            self.log(f"«{key}» услышало другое устройство")
            self.device.drain()
            return None
        self.log(f"🎙 «{key}», слушаю")
        self.show("listening")
        audio, voiced, confirmed, live_text = self.listen_live(self.device.take_preroll(), require_wake=True)
        watch = Stopwatch()
        heard = self.transcribe(audio) if voiced else ""
        watch.lap("речь→текст")
        if self.log_text:
            self.log(f"whisper: «{heard}» vosk: «{live_text}» ({len(audio) / self.device.sample_rate:.1f} с)")
        verified, command = strip_wake(heard)
        if self.verify and not verified and not confirmed:
            self.log(f"ложное срабатывание: «{heard}»" if self.log_text else "ложное срабатывание")
            return None
        if not verified:
            command = self.after_wake(heard, live_text) if confirmed else remove_wake(heard)
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
            with brain.turn_lock:
                answer = brain.assistant.handle(command, device.name)
            watch.lap("модель")
            self.log(f"Боб: {answer or '(молча)'}")
            if not answer:
                break
            voice = self.voice
            self.show("answer", command, answer)
            window = self.listen_cfg["followup_seconds"]
            if voice:
                chunks = scaled(brain.tts.stream(answer, brain.tts.voice_for(key)), brain.settings.volume(device.name))
                first = next(chunks, None)
                watch.lap("синтез")
                self.log(f"⏱ {watch.line()}")
                if first is not None:
                    self.wake.reset()
                    barged = device.play(itertools.chain([first], chunks), brain.tts.sample_rate, self.wake.feed if self.listen_cfg.get("barge_in") else None)
                    if barged:
                        self.log("↪ перебил")
                        return barged
            else:
                self.log(f"⏱ {watch.line()}")
                window = max(window, reading_seconds(answer))
            turns += 1
            if turns > self.listen_cfg["max_followups"] or time.monotonic() - started > self.listen_cfg["conversation_seconds"]:
                time.sleep(min(reading_seconds(answer), 6.0) if not voice else 1.5)
                break
            self.show("followup", command, answer, window)
            audio, voiced, confirmed, live_text = self.listen_live([], start_timeout=window, min_speech=self.listen_cfg["followup_min_speech"])
            watch = Stopwatch()
            command = remove_wake(self.transcribe(audio)) if voiced else ""
            watch.lap("речь→текст")
            if command:
                self.log("↪ уточнение")
