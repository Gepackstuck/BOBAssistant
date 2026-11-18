import argparse
import itertools
import sys
import time

from .config import load_config


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


def load_voice(cfg: dict):
    from .tts import SileroTts
    return SileroTts(cfg["tts"])


def run_ask(cfg: dict, text: str, speak: bool) -> None:
    from .assistant import Assistant
    assistant = Assistant(cfg)
    watch = Stopwatch()
    answer = assistant.handle(text)
    watch.lap("модель")
    print(f"Боб: {answer}")
    if speak and answer:
        from .audio import Speaker
        tts = load_voice(cfg)
        watch = Stopwatch()
        samples = tts.synth(answer)
        watch.lap("синтез")
        Speaker(cfg["audio"]["output_device"]).play(samples, tts.sample_rate)
    print(f"⏱ {watch.line()}")


def run_say(cfg: dict, text: str) -> None:
    from .audio import Speaker
    tts = load_voice(cfg)
    Speaker(cfg["audio"]["output_device"]).play(tts.synth(text), tts.sample_rate)


def run_voice(cfg: dict) -> None:
    from .assistant import Assistant
    from .audio import Mic, Speaker
    from .listen import Vad, capture
    from .stt import Whisper
    from .wake import VoskWake, remove_wake, strip_wake

    audio_cfg = cfg["audio"]
    started = time.perf_counter()
    print("Загружаю модели…")
    assistant = Assistant(cfg)
    assistant.llm.warm_up()
    tts = load_voice(cfg)
    whisper = Whisper(cfg["stt"])
    wake = VoskWake(cfg["wake"], audio_cfg["sample_rate"])
    vad = Vad(cfg["listen"]["speech_threshold"])
    print(f"Готово за {time.perf_counter() - started:.1f} с. Скажите «Боб», «Миньон», «Подручный» или «Окей, Сбер».")

    with Mic(audio_cfg["sample_rate"], audio_cfg["input_device"], audio_cfg["preroll_seconds"]) as mic:
        speaker = Speaker(audio_cfg["output_device"], mic)
        silent_blocks = 0
        while True:
            block = mic.read(timeout=1)
            if block is None:
                continue
            if silent_blocks >= 0:
                silent_blocks = silent_blocks + 1 if not block.any() else -1
                if silent_blocks == 40:
                    print("⚠️ Микрофон отдаёт тишину: у терминала нет доступа к микрофону (Настройки → Конфиденциальность → Микрофон).")
                    silent_blocks = -1
            phrase = wake.feed(block)
            if not phrase:
                continue
            print(f"🎙 «{phrase}», слушаю")
            audio, voiced = capture(mic, vad, cfg["listen"], mic.take_preroll())
            watch = Stopwatch()
            heard = whisper.transcribe(audio) if voiced else ""
            watch.lap("речь→текст")
            print(f"   whisper: «{heard}» ({len(audio) / mic.sample_rate:.1f} с)")
            verified, command = strip_wake(heard)
            if not verified:
                print(f"   ложное срабатывание: «{heard}»")
                wake.reset()
                continue
            if not command:
                speaker.chime()
                audio, voiced = capture(mic, vad, cfg["listen"], [])
                watch = Stopwatch()
                heard = whisper.transcribe(audio) if voiced else ""
                watch.lap("речь→текст")
                print(f"   whisper после сигнала: «{heard}» ({len(audio) / mic.sample_rate:.1f} с)")
                command = remove_wake(heard)
            if not command:
                print("   не услышал команду")
                wake.reset()
                continue
            print(f"Вы: {command}")
            answer = assistant.handle(command)
            watch.lap("модель")
            print(f"Боб: {answer or '(молча)'}")
            if answer:
                chunks = tts.stream(answer)
                first = next(chunks, None)
                watch.lap("синтез")
                print(f"⏱ {watch.line()}")
                if first is not None:
                    speaker.play_stream(itertools.chain([first], chunks), tts.sample_rate)
            else:
                print(f"⏱ {watch.line()}")
            wake.reset()


def main() -> None:
    parser = argparse.ArgumentParser(prog="bob", description="Голосовой ассистент Боб")
    sub = parser.add_subparsers(dest="command")
    ask = sub.add_parser("ask", help="задать вопрос текстом")
    ask.add_argument("text")
    ask.add_argument("--say", action="store_true", help="озвучить ответ")
    say = sub.add_parser("say", help="произнести текст")
    say.add_argument("text")
    sub.add_parser("listen", help="слушать микрофон (по умолчанию)")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    cfg = load_config()
    if args.command == "ask":
        run_ask(cfg, args.text, args.say)
    elif args.command == "say":
        run_say(cfg, args.text)
    else:
        try:
            run_voice(cfg)
        except KeyboardInterrupt:
            print("\nПока!")


if __name__ == "__main__":
    main()
