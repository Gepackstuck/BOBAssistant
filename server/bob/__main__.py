import argparse
import sys
import threading
import time

from .config import load_config
from .pipeline import Stopwatch


def load_voice(cfg: dict):
    from .tts import SileroTts
    return SileroTts(cfg["tts"])


def pick_voice(tts, cfg: dict, name: str | None, speaker: str | None, speed: float | None) -> dict:
    base = dict(tts.voices[name or cfg["tts"]["default_voice"]])
    return {**base, **({"speaker": speaker} if speaker else {}), **({"speed": speed} if speed else {})}


def run_ask(cfg: dict, text: str, speak: bool, voice_name: str | None = None) -> None:
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
        samples = tts.synth(answer, pick_voice(tts, cfg, voice_name, None, None))
        watch.lap("синтез")
        Speaker(cfg["audio"]["output_device"]).play(samples, tts.sample_rate)
    print(f"⏱ {watch.line()}")


def run_say(cfg: dict, text: str, voice_name: str | None, speaker: str | None, speed: float | None) -> None:
    from .audio import Speaker
    tts = load_voice(cfg)
    voice = pick_voice(tts, cfg, voice_name, speaker, speed)
    Speaker(cfg["audio"]["output_device"]).play(tts.synth(text, voice), tts.sample_rate)


def run_announce(cfg: dict, device: str, text: str, voice: str | None) -> None:
    import json
    from websockets.sync.client import connect
    from .net import device_token
    with connect(f"ws://127.0.0.1:{cfg['network']['port']}") as ws:
        ws.send(json.dumps({"type": "hello", "role": "control", "token": device_token(cfg)}))
        ws.send(json.dumps({"type": "announce", "device": device, "text": text, "voice": voice}, ensure_ascii=False))
        print(json.loads(ws.recv(timeout=120))["result"])


def run_levels(cfg: dict) -> None:
    import json
    import time as clock
    from websockets.sync.client import connect
    from .net import device_token
    with connect(f"ws://127.0.0.1:{cfg['network']['port']}") as ws:
        ws.send(json.dumps({"type": "hello", "role": "control", "token": device_token(cfg)}))
        for _ in range(10):
            ws.send(json.dumps({"type": "levels"}))
            print(json.loads(ws.recv(timeout=10))["result"], flush=True)
            clock.sleep(1)


def run_voice(cfg: dict, use_mic: bool) -> None:
    from .assistant import Assistant
    from .audio import Mic, Speaker
    from .devices import LocalDevice
    from .net import DeviceServer
    from .pipeline import Brain, Listener
    from .stt import Whisper

    audio_cfg = cfg["audio"]
    started = time.perf_counter()
    print("Загружаю модели…")
    assistant = Assistant(cfg)
    assistant.llm.warm_up()
    brain = Brain(cfg, assistant, Whisper(cfg["stt"]), load_voice(cfg))
    DeviceServer(cfg, brain).start()
    print(f"Готово за {time.perf_counter() - started:.1f} с. Скажите «Боб», «Миньон», «Подручный» или «Окей, Сбер».")
    if not use_mic:
        threading.Event().wait()
    with Mic(audio_cfg["sample_rate"], audio_cfg["input_device"], audio_cfg["preroll_seconds"]) as mic:
        listener = Listener(LocalDevice("mac", mic, Speaker(audio_cfg["output_device"], mic)), brain)
        listener.start()
        listener.join()


def main() -> None:
    parser = argparse.ArgumentParser(prog="bob", description="Голосовой ассистент Боб")
    sub = parser.add_subparsers(dest="command")
    ask = sub.add_parser("ask", help="задать вопрос текстом")
    ask.add_argument("text")
    ask.add_argument("--say", action="store_true", help="озвучить ответ")
    ask.add_argument("--voice", help="профиль голоса из config.yaml (alisa, minion)")
    say = sub.add_parser("say", help="произнести текст")
    say.add_argument("text")
    say.add_argument("--voice", help="профиль голоса из config.yaml (alisa, minion)")
    say.add_argument("--speaker", help="голос Silero: aidar, baya, kseniya, xenia, eugene")
    say.add_argument("--speed", type=float, help="ускорение и высота, например 1.35")
    announce = sub.add_parser("announce", help="сказать фразу на подключённом устройстве")
    announce.add_argument("device")
    announce.add_argument("text")
    announce.add_argument("--voice", help="профиль голоса из config.yaml (alisa, minion)")
    sub.add_parser("levels", help="уровень звука с подключённых устройств, 10 секунд")
    listen = sub.add_parser("listen", help="слушать микрофон Мака и устройства (по умолчанию)")
    listen.add_argument("--no-mic", action="store_true", help="не слушать микрофон Мака, только устройства")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    cfg = load_config()
    if args.command == "ask":
        run_ask(cfg, args.text, args.say, args.voice)
    elif args.command == "levels":
        run_levels(cfg)
    elif args.command == "announce":
        run_announce(cfg, args.device, args.text, args.voice)
    elif args.command == "say":
        run_say(cfg, args.text, args.voice, args.speaker, args.speed)
    else:
        try:
            run_voice(cfg, not getattr(args, "no_mic", False))
        except KeyboardInterrupt:
            print("\nПока!")


if __name__ == "__main__":
    main()
