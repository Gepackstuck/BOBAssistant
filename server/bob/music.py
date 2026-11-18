import contextvars
import difflib
import json
import re
import threading
import time
from dataclasses import dataclass, field

from yandex_music import Client

from .config import ROOT
from .pronounce import latin_to_speech

TOKEN_PATH = ROOT / "secrets" / "yandex_music_token.json"
WAVE = "user:onyourwave"
VOLUME_STEP = 0.15
MAX_BITRATE = 192
MATCH_SHARE = 0.6
NOT_FOUND = "по запросу «{}» нет подходящего исполнителя, песни или альбома. Не угадывай и не придумывай, кто это: скажи, что не расслышал, и попроси повторить название."
KINDS = ("auto", "track", "artist", "album", "playlist", "wave")

current_device = contextvars.ContextVar("current_device", default="mac")

TASTE_PATH = ROOT / "data" / "taste.json"
TASTE_TTL = 24 * 3600
TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"],
))
WRONG_RE = re.compile(r"^\s*(?:нет[,\s]+)?(?:не\s+то|не\s+тот|не\s+та|не\s+этот|не\s+эту|другой|другая|другое)\b", re.IGNORECASE)


def translit(text: str) -> str:
    return "".join(TRANSLIT.get(char, char) for char in text.lower())


def same_artist(chosen: str, other: str) -> bool:
    return difflib.SequenceMatcher(None, translit(chosen), translit(other)).ratio() >= 0.8


def words(text: str) -> list[str]:
    return re.findall(r"\w+", latin_to_speech(text).lower().replace("ё", "е"))


def close(first: str, second: str) -> bool:
    if len(first) >= 4 and len(second) >= 4 and (first in second or second in first):
        return True
    return difflib.SequenceMatcher(None, first, second).ratio() >= 0.75


def covers(wanted: str, title: str, artists: list[str]) -> bool:
    wanted_words = words(wanted)
    have = words(" ".join([title, *artists]))
    found = sum(1 for word in wanted_words if any(close(word, other) for other in have))
    return bool(wanted_words) and found / len(wanted_words) >= MATCH_SHARE


def candidate_matches(wanted: str, candidate) -> bool:
    return covers(wanted, candidate.title or "", [artist.name for artist in (candidate.artists or [])])

PAUSE_RE = re.compile(r"^\s*(?:поставь\s+на\s+паузу|пауза|приостанови(?:\s+музыку)?)\b", re.IGNORECASE)
RESUME_RE = re.compile(r"^\s*(?:продолжи|продолжай|возобнови|играй\s+дальше|сними\s+с\s+паузы)\b", re.IGNORECASE)
NEXT_RE = re.compile(r"^\s*(?:следующ\w+|дальше|пропусти|переключи(?:\s+(?:трек|песню))?)\b", re.IGNORECASE)
PREVIOUS_RE = re.compile(r"^\s*(?:предыдущ\w+|верни\s+(?:назад|предыдущ\w+)|назад)\b", re.IGNORECASE)
STOP_RE = re.compile(r"(?:выключи|останови|отключи|заверши)\s+(?:музыку|песню|воспроизведение)|^\s*стоп\s+музык\w+", re.IGNORECASE)
LOUDER_RE = re.compile(r"^\s*(?:сделай\s+)?громче\b|добавь\s+громкость", re.IGNORECASE)
QUIETER_RE = re.compile(r"^\s*(?:сделай\s+)?тише\b|убавь\s+громкость", re.IGNORECASE)
LIKE_RE = re.compile(r"^\s*(?:поставь\s+)?лайк\b|^\s*мне\s+нравится", re.IGNORECASE)
DISLIKE_RE = re.compile(r"^\s*(?:поставь\s+)?дизлайк\b|мне\s+не\s+нравится|^\s*не\s+нравится", re.IGNORECASE)
NOW_RE = re.compile(r"что\s+(?:сейчас\s+)?играет|как\s+называется\s+(?:эта\s+)?(?:песня|трек)|кто\s+(?:это\s+)?поёт", re.IGNORECASE)


@dataclass
class Item:
    track: object
    title: str
    artist: str

    def label(self) -> str:
        return f"«{self.title}», {self.artist}"


@dataclass
class Resolved:
    items: list
    name: str
    alternatives: list = field(default_factory=list)


@dataclass
class Session:
    queue: list[Item] = field(default_factory=list)
    index: int = 0
    state: str = "stopped"
    wave: bool = False
    ducked: bool = False
    volume: float = 0.8
    position: int = 0
    reported_playing: bool = False
    alternatives: list = field(default_factory=list)


def to_item(track) -> Item:
    artists = ", ".join(artist.name for artist in (track.artists or [])[:2]) or "неизвестный исполнитель"
    return Item(track, track.title, artists)


class Music:
    def __init__(self, cfg: dict):
        self.default_volume = float(cfg.get("music", {}).get("volume", 0.8))
        self.client: Client | None = None
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.devices: dict = {}

    def bind(self, devices: dict) -> None:
        self.devices = devices

    def connected(self) -> bool:
        return TOKEN_PATH.exists()

    def api(self) -> Client:
        if self.client is None:
            if not TOKEN_PATH.exists():
                raise RuntimeError("Яндекс Музыка не подключена")
            token = json.loads(TOKEN_PATH.read_text())["access_token"]
            self.client = Client(token).init()
        return self.client

    def session(self, device: str) -> Session:
        return self.sessions.setdefault(device, Session(volume=self.default_volume))

    def active(self, device: str) -> bool:
        session = self.sessions.get(device)
        return bool(session and session.state in ("playing", "paused"))

    def send(self, device: str, payload: dict) -> None:
        target = self.devices.get(device)
        if target is None or not target.alive:
            raise RuntimeError(f"устройство {device} не подключено")
        target.music(payload)

    def link(self, item: Item) -> str:
        infos = [info for info in item.track.get_download_info() if info.codec == "mp3" and info.bitrate_in_kbps <= MAX_BITRATE]
        if not infos:
            infos = [info for info in item.track.get_download_info() if info.codec == "mp3"]
        best = max(infos, key=lambda info: info.bitrate_in_kbps)
        return best.get_direct_link()

    def full(self, shorts: list) -> list:
        ids = [short.track_id for short in shorts]
        return self.api().tracks(ids) if ids else []

    def wave_batch(self, after=None) -> list[Item]:
        station = self.api().rotor_station_tracks(WAVE, queue=str(after.track.id) if after else None)
        return [to_item(entry.track) for entry in (station.sequence or [])]

    def artist_alternatives(self, query: str, chosen) -> list:
        client = self.api()
        pool = []
        for text in dict.fromkeys([query, translit(query)]):
            found = client.search(text, type_="artist")
            pool.extend((found.artists.results if found and found.artists else [])[:3])
        seen, result = {chosen.id}, []
        for artist in pool:
            if artist.id not in seen and not same_artist(chosen.name, artist.name):
                seen.add(artist.id)
                result.append(artist)
        return result[:3]

    def artist_items(self, artist) -> list[Item]:
        tracks = self.api().artists_brief_info(artist.id).popular_tracks or []
        return [to_item(track) for track in tracks]

    def resolve(self, query: str, kind: str) -> Resolved:
        client = self.api()
        if kind == "wave":
            return Resolved(self.wave_batch(), "Моя волна")
        found = client.search(query, type_="all" if kind == "auto" else kind)
        target = kind
        result = None
        if kind == "auto":
            best = found.best
            if best is None:
                raise RuntimeError(NOT_FOUND.format(query))
            target, result = best.type, best.result
            if target in ("track", "album") and not candidate_matches(query, result):
                raise RuntimeError(NOT_FOUND.format(query))
        else:
            group = getattr(found, {"track": "tracks", "artist": "artists", "album": "albums", "playlist": "playlists"}[kind], None)
            results = group.results if group and group.results else []
            if kind in ("track", "album"):
                results = [candidate for candidate in results[:10] if candidate_matches(query, candidate)]
            result = results[0] if results else None
        if result is None:
            raise RuntimeError(NOT_FOUND.format(query))
        if target == "artist":
            return Resolved(self.artist_items(result), result.name, self.artist_alternatives(query, result))
        if target == "album":
            volumes = client.albums_with_tracks(result.id).volumes or []
            return Resolved([to_item(track) for volume in volumes for track in volume], result.title)
        if target == "playlist":
            return Resolved([to_item(track) for track in self.full(result.fetch_tracks())], result.title)
        return Resolved([to_item(result)], result.title)

    def play(self, query: str = "", kind: str = "auto", device: str | None = None, volume: float | None = None, artist: str | None = None, title: str | None = None) -> str:
        device = device or current_device.get()
        query = " ".join(part for part in (artist, title) if part) or query
        resolved = self.resolve(query, kind if kind in KINDS else "auto")
        if not resolved.items:
            raise RuntimeError("ничего не нашёл")
        with self.lock:
            session = self.session(device)
            session.queue, session.index, session.wave = resolved.items, 0, kind == "wave"
            session.alternatives = list(resolved.alternatives)
            if volume is not None:
                session.volume = volume
            self.start(device)
        text = f"Играет {resolved.name}: {resolved.items[0].label()}"
        if resolved.alternatives:
            text += f". Возможно, имелся в виду {resolved.alternatives[0].name}: скажи пользователю, что если это не тот, можно ответить «нет, другой»"
        return text

    def next_alternative(self, device: str) -> str:
        with self.lock:
            session = self.sessions.get(device)
            if session is None or not session.alternatives:
                return "Других вариантов нет."
            artist = session.alternatives.pop(0)
            items = self.artist_items(artist)
            if not items:
                return self.next_alternative(device)
            session.queue, session.index, session.wave = items, 0, False
            self.start(device)
            more = f" Если и это не то, есть ещё {session.alternatives[0].name}." if session.alternatives else ""
            return f"Тогда {artist.name}: {items[0].label()}.{more}"

    def start(self, device: str) -> None:
        session = self.session(device)
        item = session.queue[session.index]
        self.send(device, {"action": "play", "url": self.link(item), "title": item.title, "artist": item.artist, "volume": session.volume})
        session.state, session.ducked = "playing", False
        if session.wave and session.index >= len(session.queue) - 2:
            session.queue.extend(self.wave_batch(item))

    def step(self, device: str, delta: int) -> str:
        with self.lock:
            session = self.session(device)
            target = session.index + delta
            if target < 0:
                target = 0
            if target >= len(session.queue):
                self.stop(device)
                return "Очередь закончилась."
            session.index = target
            self.start(device)
            return f"Играет {session.queue[target].label()}"

    def stop(self, device: str) -> None:
        with self.lock:
            session = self.sessions.get(device)
            if session and session.state != "stopped":
                self.send(device, {"action": "stop"})
            self.sessions.pop(device, None)

    def control(self, action: str, device: str | None = None) -> str:
        device = device or current_device.get()
        with self.lock:
            session = self.sessions.get(device)
            if session is None or session.state == "stopped":
                return "Сейчас ничего не играет."
            if action == "status":
                item = session.queue[session.index]
                return f"{item.label()}: состояние {session.state}, позиция {session.position // 1000} с, плеер сообщает playing={session.reported_playing}, громкость {session.volume}"
            if action == "pause":
                self.send(device, {"action": "pause"})
                session.state = "paused"
                return "Пауза."
            if action == "resume":
                self.send(device, {"action": "resume"})
                session.state = "playing"
                return "Продолжаю."
            if action == "next":
                return self.step(device, 1)
            if action == "previous":
                return self.step(device, -1)
            if action == "stop":
                self.stop(device)
                return "Музыка выключена."
            if action in ("volume_up", "volume_down"):
                delta = VOLUME_STEP if action == "volume_up" else -VOLUME_STEP
                session.volume = round(min(1.0, max(0.1, session.volume + delta)), 2)
                self.send(device, {"action": "volume", "volume": session.volume})
                return f"Громкость музыки {round(session.volume * 100)} процентов."
            if action in ("like", "dislike"):
                item = session.queue[session.index]
                (item.track.like if action == "like" else item.track.dislike)()
                if action == "dislike":
                    return self.step(device, 1)
                return "Поставил лайк."
        return "Не понял команду."

    def now_playing(self, device: str | None = None) -> str:
        device = device or current_device.get()
        session = self.sessions.get(device)
        if session is None or session.state == "stopped":
            return "Сейчас ничего не играет."
        paused = " (на паузе)" if session.state == "paused" else ""
        return f"Сейчас играет {session.queue[session.index].label()}{paused}."

    def duck(self, device: str, hold: bool) -> None:
        with self.lock:
            session = self.sessions.get(device)
            if session is None:
                return
            if hold and session.state == "playing":
                self.send(device, {"action": "pause"})
                session.state, session.ducked = "paused", True
            elif not hold and session.ducked:
                self.send(device, {"action": "resume"})
                session.state, session.ducked = "playing", False

    def on_event(self, device: str, message: dict) -> None:
        event = str(message.get("event", ""))
        with self.lock:
            session = self.sessions.get(device)
            if session is None:
                return
            if event.startswith("key:"):
                action = event.split(":", 1)[1]
                try:
                    self.control(action, device)
                except Exception as error:
                    print(f"[{device}] музыка: {error}", flush=True)
                return
            if event == "position":
                session.position = int(message.get("position", 0))
                session.reported_playing = bool(message.get("playing", False))
                return
            if session.state != "playing":
                return
            if event in ("ended", "error"):
                try:
                    self.step(device, 1)
                except Exception as error:
                    print(f"[{device}] музыка: {error}", flush=True)

    def taste_names(self, limit: int = 24) -> list[str]:
        if TASTE_PATH.exists() and time.time() - TASTE_PATH.stat().st_mtime < TASTE_TTL:
            return json.loads(TASTE_PATH.read_text())[:limit]
        try:
            client = self.api()
            liked = [entry.artist.name for entry in client.users_likes_artists() if getattr(entry, "artist", None)]
            shorts = client.users_likes_tracks().tracks[:120]
            counts: dict[str, int] = {}
            for track in client.tracks([short.track_id for short in shorts]):
                if track.artists:
                    counts[track.artists[0].name] = counts.get(track.artists[0].name, 0) + 1
            ranked = sorted(counts, key=counts.get, reverse=True)
            names = list(dict.fromkeys([*liked, *ranked]))
            TASTE_PATH.parent.mkdir(parents=True, exist_ok=True)
            TASTE_PATH.write_text(json.dumps(names, ensure_ascii=False))
            return names[:limit]
        except Exception:
            return []

    def fast(self, text: str, device: str) -> str | None:
        if WRONG_RE.search(text) and self.sessions.get(device) and self.sessions[device].alternatives:
            return self.next_alternative(device)
        if NOW_RE.search(text):
            return self.now_playing(device)
        if not self.active(device):
            return None
        for pattern, action in (
            (STOP_RE, "stop"), (PAUSE_RE, "pause"), (RESUME_RE, "resume"), (NEXT_RE, "next"),
            (PREVIOUS_RE, "previous"), (LOUDER_RE, "volume_up"), (QUIETER_RE, "volume_down"),
            (DISLIKE_RE, "dislike"), (LIKE_RE, "like"),
        ):
            if pattern.search(text):
                return self.control(action, device)
        return None


def specs(music: Music) -> list[dict]:
    return [
        {
            "name": "play_music",
            "description": "Включить музыку из Яндекс Музыки: исполнитель, песня, альбом, плейлист или «Моя волна». Вызывай на просьбы «включи/поставь/сыграй …» про музыку. Для настроения и жанров («что-нибудь спокойное») используй kind=wave.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Что искать, если непонятно, исполнитель это или песня. Для kind=wave можно пусто."},
                    "artist": {"type": "string", "description": "Исполнитель, если он назван. Пиши так, как сказал пользователь, даже по-русски («мэдкид»)."},
                    "title": {"type": "string", "description": "Название песни или альбома, если оно названо."},
                    "kind": {"type": "string", "enum": list(KINDS), "description": "auto — сам определит по поиску. Если назван исполнитель и песня, ставь track; исполнитель и альбом — album."},
                },
                "required": [],
                "additionalProperties": False,
            },
            "run": lambda args: music.play(args.get("query", ""), args.get("kind", "auto"), artist=args.get("artist"), title=args.get("title")),
        },
        {
            "name": "music_control",
            "description": "Управление музыкой, которая уже играет: пауза, продолжить, следующий или предыдущий трек, остановить, громкость музыки, лайк и дизлайк.",
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string", "enum": ["pause", "resume", "next", "previous", "stop", "volume_up", "volume_down", "like", "dislike"]}},
                "required": ["action"],
                "additionalProperties": False,
            },
            "run": lambda args: music.control(args["action"]),
        },
        {
            "name": "now_playing",
            "description": "Что сейчас играет: название и исполнитель.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "run": lambda args: music.now_playing(),
        },
    ]
