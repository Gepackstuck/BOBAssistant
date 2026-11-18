import itertools
import threading
import time

from .devices import Device
from .listen import Vad, capture
from .wake import make_wake, remove_wake, strip_wake


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


class Brain:
    def __init__(self, cfg: dict, assistant, whisper, tts):
        self.cfg = cfg
        self.assistant = assistant
        self.whisper = whisper
        self.tts = tts
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

    def log(self, message: str) -> None:
        print(f"[{self.device.name}] {message}", flush=True)

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
            if key:
                try:
                    self.handle(key)
                except Exception as error:
                    self.log(f"ошибка: {error}")
                    self.device.show("idle")
                finally:
                    self.wake.reset()
        self.log("отключено")

    def handle(self, key: str) -> None:
        if not self.brain.claim(self.device.name):
            self.log(f"«{key}» услышало другое устройство")
            self.device.drain()
            return
        self.log(f"🎙 «{key}», слушаю")
        self.device.show("listening")
        audio, voiced = capture(self.device, self.vad, self.listen_cfg, self.device.take_preroll())
        watch = Stopwatch()
        heard = self.brain.transcribe(audio) if voiced else ""
        watch.lap("речь→текст")
        if self.log_text:
            self.log(f"whisper: «{heard}» ({len(audio) / self.device.sample_rate:.1f} с)")
        verified, command = strip_wake(heard)
        if self.verify and not verified:
            self.log(f"ложное срабатывание: «{heard}»" if self.log_text else "ложное срабатывание")
            self.device.show("idle")
            return
        if not verified:
            command = remove_wake(heard)
        if not command:
            self.device.chime()
            audio, voiced = capture(self.device, self.vad, self.listen_cfg, [])
            watch = Stopwatch()
            command = remove_wake(self.brain.transcribe(audio)) if voiced else ""
            watch.lap("речь→текст")
        if not command:
            self.log("не услышал команду")
            self.device.show("idle")
            return
        self.converse(key, command, watch)

    def converse(self, key: str, command: str, watch: Stopwatch) -> None:
        while command:
            self.log(f"Вы: {command}")
            self.device.show("heard", command)
            with self.brain.turn_lock:
                answer = self.brain.assistant.handle(command)
            watch.lap("модель")
            self.log(f"Боб: {answer or '(молча)'}")
            if not answer:
                break
            self.device.show("answer", answer)
            chunks = self.brain.tts.stream(answer, self.brain.tts.voice_for(key))
            first = next(chunks, None)
            watch.lap("синтез")
            self.log(f"⏱ {watch.line()}")
            if first is not None:
                self.device.play(itertools.chain([first], chunks), self.brain.tts.sample_rate)
            self.device.show("followup")
            audio, voiced = capture(self.device, self.vad, self.listen_cfg, [], self.listen_cfg["followup_seconds"])
            watch = Stopwatch()
            command = remove_wake(self.brain.transcribe(audio)) if voiced else ""
            watch.lap("речь→текст")
            if command:
                self.log("↪ уточнение")
        self.device.show("idle")
