import Foundation

final class Link {
    var onPlate: ((PlateState) -> Void)?
    var onLamp: ((LampState) -> Void)?
    var onCard: ((CardState) -> Void)?
    var onSettings: ((Bool, String, Int, String) -> Void)?
    var onConnection: ((Bool) -> Void)?

    private let url: URL
    private let token: String
    private let device: String
    private var session = URLSession(configuration: .default)
    private var task: URLSessionWebSocketTask?
    private var backoff = 1.0
    private var stopped = false

    init(url: URL, token: String, device: String) {
        self.url = url
        self.token = token
        self.device = device
    }

    func start() {
        stopped = false
        connect()
    }

    func stop() {
        stopped = true
        task?.cancel(with: .goingAway, reason: nil)
    }

    func setVoice(_ enabled: Bool) {
        send(["type": "set_voice", "enabled": enabled])
    }

    func setVolume(_ percent: Int) {
        send(["type": "set_volume", "percent": percent])
    }

    func setIndicator(_ style: String) {
        send(["type": "set_indicator", "style": style])
    }

    func setTheme(_ theme: String) {
        send(["type": "set_theme", "theme": theme])
    }

    private func send(_ payload: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let text = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(text)) { _ in }
    }

    private func connect() {
        guard !stopped else { return }
        let socket = session.webSocketTask(with: url)
        task = socket
        socket.resume()
        send(["type": "hello", "role": "display", "device": device, "token": token])
        receive(on: socket)
    }

    private func receive(on socket: URLSessionWebSocketTask) {
        socket.receive { [weak self] result in
            guard let self, socket === self.task else { return }
            switch result {
            case .failure:
                self.retry()
            case .success(let message):
                if case .string(let text) = message {
                    self.handle(text)
                }
                self.receive(on: socket)
            }
        }
    }

    private func handle(_ text: String) {
        guard let data = text.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = object["type"] as? String else { return }
        DispatchQueue.main.async {
            self.backoff = 1.0
            self.onConnection?(true)
            switch type {
            case "plate":
                self.onPlate?(PlateState(
                    phase: object["phase"] as? String ?? "idle",
                    request: object["request"] as? String ?? "",
                    answer: object["answer"] as? String ?? "",
                    voice: object["voice"] as? Bool ?? true,
                    theme: object["theme"] as? String ?? "dark",
                    window: (object["window"] as? NSNumber)?.doubleValue ?? 0
                ))
            case "lamp":
                let rgb = (object["rgb"] as? [NSNumber])?.map { $0.doubleValue / 255 } ?? [1, 0.8, 0.5]
                self.onLamp?(LampState(
                    name: object["name"] as? String ?? "Лампа",
                    on: object["on"] as? Bool ?? false,
                    red: rgb.count > 0 ? rgb[0] : 1, green: rgb.count > 1 ? rgb[1] : 0.8, blue: rgb.count > 2 ? rgb[2] : 0.5,
                    brightness: (object["brightness"] as? NSNumber)?.intValue ?? 0,
                    pending: object["pending"] as? Bool ?? false
                ))
            case "music_card":
                self.onCard?(CardState(
                    visible: object["visible"] as? Bool ?? false,
                    title: object["title"] as? String ?? "",
                    artist: object["artist"] as? String ?? "",
                    cover: object["cover"] as? String ?? "",
                    paused: (object["state"] as? String) == "paused"
                ))
            case "settings":
                self.onSettings?(object["voice"] as? Bool ?? true, object["theme"] as? String ?? "dark", (object["volume"] as? NSNumber)?.intValue ?? 100, object["indicator"] as? String ?? "classic")
            default:
                break
            }
        }
    }

    private func retry() {
        DispatchQueue.main.async {
            self.onConnection?(false)
            guard !self.stopped else { return }
            let delay = self.backoff
            self.backoff = min(self.backoff * 2, 15)
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { self.connect() }
        }
    }
}
