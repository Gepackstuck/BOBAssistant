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


class DryDevice:
    alive = True

    def music(self, payload: dict) -> None:
        details = f" {payload.get('title', '')} — {payload.get('artist', '')}" if payload.get("action") == "play" else ""
        print(f"   ♪ {payload['action']}{details}")


def run_ask(cfg: dict, text: str, speak: bool, voice_name: str | None = None) -> None:
    from .assistant import Assistant
    from .settings import DeviceSettings
    assistant = Assistant(cfg, DeviceSettings())
    assistant.music.bind({"mac": DryDevice()})
    watch = Stopwatch()
    answer = assistant.handle(text)
    watch.lap("модель")
    print(f"Боб: {answer}")
    if speak and answer:
        from .audio import Speaker
        tts = load_voice(cfg)
        watch = Stopwatch()
        samples = tts.synth(answer.partition('|||')[0], pick_voice(tts, cfg, voice_name, None, None))
        watch.lap("синтез")
        Speaker(cfg["audio"]["output_device"]).play(samples, tts.sample_rate)
    print(f"⏱ {watch.line()}")


def run_ask_live(cfg: dict, device: str, text: str) -> None:
    import json
    from websockets.sync.client import connect
    from .net import device_token
    with connect(f"ws://127.0.0.1:{cfg['network']['port']}") as ws:
        ws.send(json.dumps({"type": "hello", "role": "control", "token": device_token(cfg)}))
        ws.send(json.dumps({"type": "ask", "device": device, "text": text}))
        print(json.loads(ws.recv(timeout=120)).get("result"))


def run_style(cfg: dict, device: str, name: str) -> None:
    import json
    from websockets.sync.client import connect
    from .net import device_token
    with connect(f"ws://127.0.0.1:{cfg['network']['port']}") as ws:
        ws.send(json.dumps({"type": "hello", "role": "control", "token": device_token(cfg)}))
        ws.send(json.dumps({"type": "set_style", "device": device, "style": name}))
        print(json.loads(ws.recv(timeout=10)).get("result"))


def run_eval(cfg: dict, path: str, out: str | None) -> None:
    from pathlib import Path
    from .assistant import Assistant
    from .settings import DeviceSettings
    assistant = Assistant(cfg, DeviceSettings())
    assistant.music.bind({"mac": DryDevice()})
    lines = [f"# Сравнение: модель {cfg['llm'].get('model')}", ""]
    fresh = True
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if raw.startswith("#"):
            continue
        if not raw.strip():
            fresh = True
            continue
        if fresh:
            assistant.session = assistant.llm.new_session()
            fresh = False
        watch = Stopwatch()
        answer = assistant.handle(raw.strip(), "mac")
        watch.lap("модель")
        spoken, _, extra = answer.partition("|||")
        print(f"Вы: {raw.strip()}\nБоб: {spoken}" + (f" ‖ {extra}" if extra else "") + f"\n⏱ {watch.line()}\n")
        lines += [f"**{raw.strip()}**", f"- голосом: {spoken}", *([f"- на плашке: {extra}"] if extra else []), f"- время: {watch.marks[0][1]:.1f} с", ""]
    if out:
        Path(out).write_text("\n".join(lines), encoding="utf-8")


def run_say(cfg: dict, text: str, voice_name: str | None, speaker: str | None, speed: float | None) -> None:
    from .audio import Speaker
    tts = load_voice(cfg)
    voice = pick_voice(tts, cfg, voice_name, speaker, speed)
    Speaker(cfg["audio"]["output_device"]).play(tts.synth(text, voice), tts.sample_rate)


def run_music(cfg: dict, query: str, kind: str) -> None:
    import httpx
    from .music import Music
    music = Music(cfg)
    resolved = music.resolve(query, kind)
    items = resolved.items
    print(f"Найдено: {resolved.name}, треков в очереди: {len(items)}")
    for index, item in enumerate(items[:5], 1):
        print(f"  {index}. {item.label()}")
    if resolved.alternatives:
        print("Другие варианты:", ", ".join(artist.name for artist in resolved.alternatives))
    url = music.link(items[0])
    head = httpx.head(url, follow_redirects=True, timeout=10)
    print(f"Ссылка на первый трек: HTTP {head.status_code}, {int(head.headers.get('content-length', 0)) / 1e6:.1f} МБ")


def run_control(cfg: dict, payload: dict) -> None:
    import json
    from websockets.sync.client import connect
    from .net import device_token
    with connect(f"ws://127.0.0.1:{cfg['network']['port']}") as ws:
        ws.send(json.dumps({"type": "hello", "role": "control", "token": device_token(cfg)}))
        ws.send(json.dumps(payload, ensure_ascii=False))
        print(json.loads(ws.recv(timeout=120))["result"])


def run_demo(cfg: dict, device: str, voice: bool, scale: float, theme: str | None = None) -> None:
    import json
    from websockets.sync.client import connect
    from .net import device_token
    with connect(f"ws://127.0.0.1:{cfg['network']['port']}") as ws:
        ws.send(json.dumps({"type": "hello", "role": "control", "token": device_token(cfg)}))
        ws.send(json.dumps({"type": "demo", "device": device, "voice": voice, "scale": scale, "theme": theme}))
        print(json.loads(ws.recv(timeout=300))["result"])


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
    from .devices import Displays, LocalDevice
    from .net import DeviceServer
    from .pipeline import Brain, Listener
    from .settings import DeviceSettings
    from .stt import Whisper

    audio_cfg = cfg["audio"]
    started = time.perf_counter()
    print("Загружаю модели…")
    settings = DeviceSettings()
    assistant = Assistant(cfg, settings)
    assistant.llm.warm_up()
    whisper = Whisper(cfg["stt"])
    names = list(dict.fromkeys([*cfg["stt"].get("names", []), *assistant.music.taste_names()]))
    if names:
        whisper.prompt = f"{whisper.prompt} Исполнители: {', '.join(names)}."
        whisper.names = {name.lower() for name in names}
    brain = Brain(cfg, assistant, whisper, load_voice(cfg), settings)
    if cfg["stt"].get("phonetic", True):
        from .phonetic import Phonetic
        brain.phonetic = Phonetic()
        brain.phonetic.start()
    displays = Displays()
    server = DeviceServer(cfg, brain, displays)
    server.start()
    assistant.planner.on_fire = server.fire
    assistant.home.notify = lambda device, payload: server.devices[device].card(payload) if device in server.devices else None
    assistant.planner.start()
    print(f"Готово за {time.perf_counter() - started:.1f} с. Скажите «Джарвис».")
    if not use_mic:
        threading.Event().wait()
    with Mic(audio_cfg["sample_rate"], audio_cfg["input_device"], audio_cfg["preroll_seconds"]) as mic:
        local = LocalDevice("mac", mic, Speaker(audio_cfg["output_device"], mic), displays)
        server.devices["mac"] = local
        local.music_listener = lambda message: assistant.music.on_event("mac", message)
        listener = Listener(local, brain)
        listener.start()
        listener.join()


def run_observe(cfg: dict, source: str) -> None:
    from .audio import Mic, Speaker
    from .devices import Displays, LocalDevice
    from .events import emit
    from .net import DeviceServer
    from .pipeline import Brain, Listener
    from .settings import DeviceSettings
    from .stt import Whisper

    audio_cfg = cfg["audio"]
    cfg["debug"]["log_text"] = True
    print("Загружаю модели…")
    whisper = Whisper(cfg["stt"])
    settings = DeviceSettings()
    brain = Brain(cfg, None, whisper, None, settings)
    from .phonetic import Phonetic
    brain.phonetic = Phonetic()
    brain.phonetic.start()
    emit("session", mode=f"наблюдение, источник: {'микрофон ТВ' if source == 'tv' else 'микрофон Мака'}, без ответов")
    print("Наблюдаю: пишу журнал и запись звука, не отвечаю.")
    if source == "tv":
        server = DeviceServer(cfg, brain, Displays(), observe=True)
        server.start()
        threading.Event().wait()
    with Mic(audio_cfg["sample_rate"], audio_cfg["input_device"], audio_cfg["preroll_seconds"]) as mic:
        local = LocalDevice("mac", mic, Speaker(audio_cfg["output_device"], mic), Displays())
        listener = Listener(local, brain, observe=True)
        listener.start()
        listener.join()


class ReplayDevice:
    name = "tv"
    sample_rate = 16000

    def __init__(self, audio):
        from collections import deque
        from .audio import BLOCK
        self.audio = audio
        self.block = BLOCK
        self.position = 0
        self.preroll = deque(maxlen=int(3.0 * self.sample_rate / BLOCK))

    @property
    def alive(self) -> bool:
        return self.position + self.block <= len(self.audio)

    def read(self, timeout=None):
        if not self.alive:
            return None
        block = self.audio[self.position:self.position + self.block]
        self.position += self.block
        self.preroll.append(block)
        return block

    def take_preroll(self):
        blocks = list(self.preroll)
        self.preroll.clear()
        return blocks

    def drain(self) -> None:
        self.preroll.clear()

    def plate(self, *args, **kwargs) -> None:
        return None

    def media(self, hold: bool) -> None:
        return None

    def chime(self) -> None:
        return None


def run_replay(cfg: dict, path: str) -> None:
    import json
    from pathlib import Path
    from . import events
    from .bench import load_wav
    from .phonetic import Phonetic
    from .pipeline import Brain, Listener
    from .settings import DeviceSettings
    from .stt import Whisper

    out = Path(path).with_suffix(".replay.jsonl")
    out.unlink(missing_ok=True)
    events.EVENTS = out
    cfg["debug"]["log_text"] = True
    cfg["debug"]["keep_triggers"] = 0
    brain = Brain(cfg, None, Whisper(cfg["stt"]), None, DeviceSettings())
    brain.phonetic = Phonetic()
    brain.phonetic.start()
    while not brain.phonetic.available:
        time.sleep(0.5)
    device = ReplayDevice(load_wav(Path(path)))
    listener = Listener(device, brain, observe=True)
    listener.record = False
    listener.start()
    listener.join()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    total = len(device.audio) / device.sample_rate
    deaf = sum(row["audio"] or 0 for row in rows if row["kind"] == "busy")
    count = lambda kind: sum(1 for row in rows if row["kind"] == kind)
    print(f"запись {total:.0f} с: срабатываний {count('wake')}, отклонено {count('rejected')}, принято {count('accepted')}, перезапусков по новому слову {count('rearmed')}, глухое время {deaf:.0f} с ({100 * deaf / total:.0f}%)")
    for row in rows:
        if row["kind"] in ("accepted", "rejected", "rearmed"):
            print(f"  {row['kind']}: {row.get('stage', '')} {row.get('whisper', row.get('giga', ''))[:90]}")


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
    demo = sub.add_parser("plate-demo", help="показать на устройстве плашку без звука")
    demo.add_argument("device")
    demo.add_argument("--no-voice", action="store_true", help="показать вариант «только текст»")
    demo.add_argument("--theme", choices=["dark", "light"], help="показать тёмную или светлую плашку")
    demo.add_argument("--slow", type=float, default=1.0, help="во сколько раз замедлить, например 3")
    music = sub.add_parser("music", help="найти музыку и проверить ссылку, не играя")
    music.add_argument("query")
    music.add_argument("--kind", default="auto", choices=["auto", "track", "artist", "album", "playlist", "wave"])
    play = sub.add_parser("music-play", help="включить музыку на подключённом устройстве")
    play.add_argument("device")
    play.add_argument("query")
    play.add_argument("--kind", default="auto")
    play.add_argument("--volume", type=float, help="громкость плеера 0..1 (0 — без звука)")
    control = sub.add_parser("music-control", help="pause, resume, next, previous, stop, volume_up, volume_down")
    control.add_argument("device")
    control.add_argument("action")
    evaluate = sub.add_parser("eval", help="прогнать эталонные фразы через ассистента без звука и музыки")
    evaluate.add_argument("--file", default="../docs/reference-phrases.txt")
    evaluate.add_argument("--out", help="сохранить результат в markdown")
    style = sub.add_parser("style", help="переключить оформление ответов устройства (plate или corner)")
    style.add_argument("device")
    style.add_argument("name", choices=["plate", "corner"])
    live = sub.add_parser("ask-live", help="отправить фразу работающему Бобу как с устройства (без звука), ответ в консоль")
    live.add_argument("device")
    live.add_argument("text")
    observe = sub.add_parser("observe", help="слушать, вести журнал и запись, ничего не отвечать")
    observe.add_argument("--source", choices=["tv", "mac"], default="tv", help="чей микрофон слушать (по умолчанию ТВ)")
    bench = sub.add_parser("bench", help="сравнить модели распознавания на записи")
    bench.add_argument("wav")
    bench.add_argument("--models", default="whisper-large-v3,whisper-turbo,gigaam")
    bench.add_argument("--minutes", type=float, help="взять только первые N минут")
    replay = sub.add_parser("replay", help="прогнать запись через детектор и проверки без ответов, посчитать глухое время")
    replay.add_argument("wav")
    sub.add_parser("monitor", help="живая статистика из журнала событий")
    sub.add_parser("yandex-login", help="войти в Яндекс Музыку по коду и сохранить токен")
    sub.add_parser("levels", help="уровень звука с подключённых устройств, 10 секунд")
    listen = sub.add_parser("listen", help="слушать микрофон Мака и устройства (по умолчанию)")
    listen.add_argument("--no-mic", action="store_true", help="не слушать микрофон Мака, только устройства")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    cfg = load_config()
    if args.command == "ask":
        run_ask(cfg, args.text, args.say, args.voice)
    elif args.command == "ask-live":
        run_ask_live(cfg, args.device, args.text)
    elif args.command == "style":
        run_style(cfg, args.device, args.name)
    elif args.command == "eval":
        run_eval(cfg, args.file, args.out)
    elif args.command == "music":
        run_music(cfg, args.query, args.kind)
    elif args.command == "music-play":
        run_control(cfg, {"type": "music_play", "device": args.device, "query": args.query, "kind": args.kind, "volume": args.volume})
    elif args.command == "music-control":
        run_control(cfg, {"type": "music_control", "device": args.device, "action": args.action})
    elif args.command == "observe":
        try:
            run_observe(cfg, args.source)
        except KeyboardInterrupt:
            print("\nПока!")
    elif args.command == "bench":
        from .bench import run_bench
        run_bench(args.wav, args.models.split(","), args.minutes)
    elif args.command == "replay":
        run_replay(cfg, args.wav)
    elif args.command == "monitor":
        from .monitor import run_monitor
        try:
            run_monitor()
        except KeyboardInterrupt:
            pass
    elif args.command == "yandex-login":
        from .yandex_login import login
        login()
    elif args.command == "plate-demo":
        run_demo(cfg, args.device, not args.no_voice, args.slow, args.theme)
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
