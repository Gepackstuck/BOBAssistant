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
PHONETIC_SCORE = 0.62
PHONETIC_MARGIN = 0.08
PHONETIC_TITLE = 0.5
COMMAND_WORDS = {"включи", "поставь", "сыграй", "запусти", "найди", "боб", "джарвис", "миньон", "подручный", "сбер", "пожалуйста", "песню", "трек", "альбом", "мне", "давай", "окей", "ок", "музыку", "от", "группы", "исполнителя"}
STATION_TYPES = ("mood", "activity", "epoch", "genre", "personal", "editorial")
STATION_HINTS = [
    (r"весел|радост|позитив", "mood:happy"), (r"бодр|энергич", "mood:energetic"), (r"расслаб|отдых", "mood:relaxed"),
    (r"для\s+сна|засып|спать|сон\b", "activity:fall-asleep"), (r"работ", "activity:work-background"),
    (r"учеб|учёб|учит|концентрац|сосредоточ", "activity:study-background"), (r"тренир|спорт|зал\b", "activity:workout"),
    (r"\bбег|пробеж", "activity:run"), (r"вечерин|тусов", "activity:party"), (r"дорог|путешеств", "activity:road-trip"),
    (r"за\s+рул|машин", "activity:driving"), (r"просыпа|утр|будильн", "activity:wake-up"), (r"романт|свидани", "activity:romantic-date"),
    (r"пятидесят", "epoch:fifties"), (r"шестидесят", "epoch:sixties"), (r"семидесят", "epoch:seventies"), (r"восьмидесят", "epoch:eighties"),
    (r"девяност", "epoch:nineties"), (r"нулев|двухтысяч", "epoch:zeroes"), (r"десят(?:ых|ые)", "epoch:tenths"), (r"двадцат(?:ых|ые)", "epoch:twenties"),
    (r"вечн\w+\s+хит", "epoch:the-greatest-hits"),
]
NOT_FOUND = "по запросу «{}» нет подходящего исполнителя, песни или альбома. Не угадывай и не придумывай, кто это: скажи, что не расслышал, и попроси повторить название."
KINDS = ("auto", "track", "artist", "album", "playlist", "wave", "station")

current_device = contextvars.ContextVar("current_device", default="mac")
phonetic_hint = contextvars.ContextVar("phonetic_hint", default="")

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
    spoken = latin_to_speech(text).lower().replace("ё", "е")
    return re.findall(r"\w+", spoken.replace("йа", "я").replace("йу", "ю").replace("йе", "е"))


def close(first: str, second: str) -> bool:
    if len(first) >= 4 and len(second) >= 4 and (first in second or second in first):
        return True
    return difflib.SequenceMatcher(None, first, second).ratio() >= 0.75


def share(wanted: str, title: str, artists: list[str]) -> float:
    wanted_words = words(wanted)
    have = words(" ".join([title, *artists]))
    found = sum(1 for word in wanted_words if any(close(word, other) for other in have))
    return found / len(wanted_words) if wanted_words else 0.0


def candidate_share(wanted: str, candidate) -> float:
    return share(wanted, candidate.title or "", [artist.name for artist in (candidate.artists or [])])


def candidate_matches(wanted: str, candidate) -> bool:
    return candidate_share(wanted, candidate) >= MATCH_SHARE


def shorter_queries(query: str) -> list[str]:
    parts = query.split()
    return [query, *(" ".join(parts[:-cut]) for cut in (1, 2) if len(parts) - cut >= 2)]

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
    station: str | None = None


@dataclass
class Session:
    queue: list[Item] = field(default_factory=list)
    index: int = 0
    state: str = "stopped"
    wave: bool = False
    station: str = WAVE
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
        self.stations: list | None = None
        self.extra_names: list[str] = list(cfg.get("stt", {}).get("names", []))

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

    def wave_batch(self, after=None, station: str = WAVE) -> list[Item]:
        batch = self.api().rotor_station_tracks(station, queue=str(after.track.id) if after else None)
        return [to_item(entry.track) for entry in (batch.sequence or [])]

    def station_list(self) -> list[tuple[str, str, list[str]]]:
        if self.stations is None:
            self.stations = [
                (f"{entry.station.id.type}:{entry.station.id.tag}", entry.station.name, words(entry.station.name))
                for entry in self.api().rotor_stations_list()
                if entry.station.id.type in STATION_TYPES
            ]
        return self.stations

    def find_station(self, text: str) -> tuple[str, str]:
        stations = self.station_list()
        lowered = text.lower().replace("ё", "е")
        hinted = next((identifier for pattern, identifier in STATION_HINTS if re.search(pattern, lowered)), None)
        if hinted:
            return next((identifier, name) for identifier, name, _ in stations if identifier == hinted)
        wanted = [word for word in words(text) if len(word) > 2]
        best, best_score = None, 0.0
        for identifier, name, name_words in stations:
            matched = sum(1 for word in wanted if any(other.startswith(word[:5]) or word.startswith(other[:5]) for other in name_words if len(other) > 2))
            score = matched / len(wanted) if wanted else 0.0
            if score > best_score or (score == best_score and best and len(name) < len(best[1])):
                best, best_score = (identifier, name), score
        if best is None or best_score < 0.99:
            raise RuntimeError(f"нет станции «{text}». Спроси, какое настроение, занятие, эпоху или жанр включить (например, спокойное, для работы, девяностые, джаз)")
        return best

    def cover_url(self, item: Item, size: str = "200x200") -> str:
        uri = getattr(item.track, "cover_uri", None)
        return f"https://{uri.replace('%%', size)}" if uri else ""

    def known_names(self) -> list[str]:
        return list(dict.fromkeys([*self.extra_names, *self.taste_names(limit=300)]))

    def phonetic_artist(self, hint: str) -> tuple[str, list[str]] | None:
        heard = words(hint)
        names = [(name, " ".join(words(name))) for name in self.known_names()]
        scored = []
        for size in range(1, 5):
            for start in range(len(heard) - size + 1):
                gram = " ".join(heard[start:start + size])
                if len(gram.replace(" ", "")) < 4 or all(word in COMMAND_WORDS for word in heard[start:start + size]):
                    continue
                for name, spoken in names:
                    if abs(len(spoken.split()) - size) <= 1 and len(spoken.replace(" ", "")) >= 4:
                        scored.append((difflib.SequenceMatcher(None, gram, spoken).ratio(), name, start, size))
        scored.sort(reverse=True)
        if not scored or scored[0][0] < PHONETIC_SCORE:
            return None
        best = scored[0]
        rival = next((item for item in scored if item[1] != best[1] and item[2] < best[2] + best[3] and best[2] < item[2] + item[3]), None)
        if rival and best[0] - rival[0] < PHONETIC_MARGIN:
            return None
        rest = [word for index, word in enumerate(heard) if not best[2] <= index < best[2] + best[3] and word not in COMMAND_WORDS]
        return best[1], rest

    def phonetic_track_score(self, rest: list[str], track) -> float:
        wanted = " ".join(rest)
        title = words(track.title or "")
        have = [*title, *(word for artist in (track.artists or []) for word in words(artist.name))]
        soft = sum(1 for word in rest if any(difflib.SequenceMatcher(None, word, other).ratio() >= 0.6 for other in have)) / len(rest)
        return max(difflib.SequenceMatcher(None, wanted, " ".join(title)).ratio(), soft)

    def phonetic_resolve(self) -> "Resolved | None":
        hint = phonetic_hint.get()
        found = self.phonetic_artist(hint) if hint else None
        if found is None:
            return None
        name, rest = found
        client = self.api()
        result = client.search(name, type_="artist")
        artists = result.artists.results if result and result.artists else []
        artist = next((candidate for candidate in artists[:5] if same_artist(candidate.name, name) or " ".join(words(candidate.name)) == " ".join(words(name))), artists[0] if artists else None)
        if artist is None:
            return None
        if rest:
            tracks = []
            for page in range(3):
                batch = client.artists_tracks(artist.id, page=page, page_size=50)
                tracks.extend(batch.tracks if batch and batch.tracks else [])
            scored = [(self.phonetic_track_score(rest, track), track) for track in tracks]
            if scored:
                score, track = max(scored, key=lambda pair: pair[0])
                if score >= PHONETIC_TITLE:
                    return Resolved([to_item(track)], track.title)
        return Resolved(self.artist_items(artist), artist.name, self.artist_alternatives(name, artist))

    def card_payload(self, device: str) -> dict:
        session = self.sessions.get(device)
        if session is None or session.state == "stopped" or not session.queue:
            return {"type": "music_card", "visible": False}
        item = session.queue[session.index]
        return {"type": "music_card", "visible": True, "title": item.title, "artist": item.artist, "cover": self.cover_url(item), "state": session.state}

    def publish_card(self, device: str) -> None:
        target = self.devices.get(device)
        if target is not None and hasattr(target, "card"):
            target.card(self.card_payload(device))

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

    def best_match(self, query: str, kind: str, attribute: str, first):
        best, best_share, seen = None, 0.0, set()
        for text in shorter_queries(query):
            found = first if text == query else self.api().search(text, type_=kind)
            group = getattr(found, attribute, None)
            for candidate in (group.results if group and group.results else [])[:20]:
                if candidate.id in seen:
                    continue
                seen.add(candidate.id)
                value = candidate_share(query, candidate)
                if value > best_share:
                    best, best_share = candidate, value
            if best_share >= 1.0:
                break
        return best if best_share >= MATCH_SHARE else None

    def resolve(self, query: str, kind: str) -> Resolved:
        client = self.api()
        if kind == "wave":
            return Resolved(self.wave_batch(), "Моя волна")
        if kind == "station":
            identifier, name = self.find_station(query)
            return Resolved(self.wave_batch(None, identifier), name, station=identifier)
        found = client.search(query, type_="all" if kind == "auto" else kind)
        target = kind
        result = None
        if kind == "auto":
            best = found.best
            if best is None:
                raise RuntimeError(NOT_FOUND.format(query))
            target, result = best.type, best.result
            if target not in ("track", "artist", "album", "playlist"):
                raise RuntimeError(NOT_FOUND.format(query))
            mismatch = (target in ("track", "album") and not candidate_matches(query, result)) or (target == "artist" and share(query, "", [result.name]) < MATCH_SHARE)
            if mismatch:
                result = self.best_match(query, "track", "tracks", client.search(query, type_="track"))
                if result is None:
                    raise RuntimeError(NOT_FOUND.format(query))
                target = "track"
        else:
            attribute = {"track": "tracks", "artist": "artists", "album": "albums", "playlist": "playlists"}[kind]
            if kind in ("track", "album"):
                result = self.best_match(query, kind, attribute, found)
            else:
                group = getattr(found, attribute, None)
                result = group.results[0] if group and group.results else None
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
        try:
            try:
                resolved = self.resolve(query, kind if kind in KINDS else "auto")
            except RuntimeError:
                if kind != "station":
                    raise
                resolved = self.resolve(query, "auto")
        except RuntimeError:
            resolved = self.phonetic_resolve()
            if resolved is None:
                raise
        if not resolved.items:
            raise RuntimeError("ничего не нашёл")
        with self.lock:
            session = self.session(device)
            session.queue, session.index, session.wave = resolved.items, 0, kind == "wave" or bool(resolved.station)
            session.station = resolved.station or WAVE
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
        self.publish_card(device)
        if session.wave and session.index >= len(session.queue) - 2:
            session.queue.extend(self.wave_batch(item, session.station))

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
        self.publish_card(device)

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
                self.publish_card(device)
                return "Пауза."
            if action == "resume":
                self.send(device, {"action": "resume"})
                session.state = "playing"
                self.publish_card(device)
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
            "description": "Включить музыку из Яндекс Музыки: исполнитель, песня, альбом, плейлист или «Моя волна». Вызывай на просьбы «включи/поставь/сыграй …» про музыку. Для настроения, занятия, эпохи и жанра («что-нибудь спокойное», «для работы», «девяностые», «джаз», «грустное») используй kind=station и в query название настроения, занятия, эпохи или жанра. Если назван исполнитель, песня или альбом, станция не нужна: kind=track, artist или album. Просто «включи музыку» или «Моя волна» — kind=wave.",
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
