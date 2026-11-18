import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let plate = PlateWindow()
    private let card = CardWindow()
    private let lamp = LampWindow()
    private var statusItem: NSStatusItem!
    private var link: Link!
    private let statusLine = NSMenuItem(title: "Нет связи с Бобом", action: nil, keyEquivalent: "")
    private let voiceItem = NSMenuItem(title: "Отвечать голосом", action: #selector(toggleVoice), keyEquivalent: "")
    private let themeItem = NSMenuItem(title: "Светлая плашка", action: #selector(toggleTheme), keyEquivalent: "")
    private let equalizerItem = NSMenuItem(title: "Разноцветный эквалайзер", action: #selector(toggleEqualizer), keyEquivalent: "")
    private var colorful = false
    private let volumeItem = NSMenuItem(title: "Громкость голоса", action: nil, keyEquivalent: "")
    private var volumeItems: [NSMenuItem] = []
    private var voiceOn = true
    private var theme = "dark"
    private var demoTimers: [Timer] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "waveform.circle", accessibilityDescription: "Боб")
        }
        let menu = NSMenu()
        statusLine.isEnabled = false
        menu.addItem(statusLine)
        menu.addItem(.separator())
        voiceItem.target = self
        voiceItem.state = .on
        menu.addItem(voiceItem)
        let volumeMenu = NSMenu()
        for percent in stride(from: 10, through: 100, by: 10) {
            let item = NSMenuItem(title: "\(percent)%", action: #selector(chooseVolume(_:)), keyEquivalent: "")
            item.target = self
            item.tag = percent
            volumeItems.append(item)
            volumeMenu.addItem(item)
        }
        volumeItem.submenu = volumeMenu
        menu.addItem(volumeItem)
        themeItem.target = self
        menu.addItem(themeItem)
        equalizerItem.target = self
        menu.addItem(equalizerItem)
        let demo = NSMenuItem(title: "Показать пример плашки", action: #selector(runDemo), keyEquivalent: "")
        demo.target = self
        menu.addItem(demo)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "Выйти", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(quit)
        statusItem.menu = menu

        let environment = ProcessInfo.processInfo.environment
        let address = environment["BOB_SERVER"] ?? "ws://127.0.0.1:8765"
        link = Link(url: URL(string: address)!, token: Self.loadToken(), device: environment["BOB_DEVICE"] ?? "mac")
        link.onPlate = { [weak self] state in self?.plate.render(state) }
        link.onLamp = { [weak self] state in
            guard let self else { return }
            self.lamp.render(state, theme: Theme.named(self.theme))
        }
        link.onCard = { [weak self] state in
            guard let self else { return }
            self.card.render(state, theme: Theme.named(self.theme))
        }
        link.onSettings = { [weak self] voice, theme, volume, indicator in self?.apply(voice: voice, theme: theme, volume: volume, indicator: indicator) }
        link.onConnection = { [weak self] connected in
            self?.statusLine.title = connected ? "Подключено к Бобу" : "Нет связи с Бобом"
            if !connected {
                self?.plate.render(PlateState(phase: "idle", request: "", answer: "", voice: true))
                self?.card.hide()
            }
        }
        link.start()
    }

    static func loadToken() -> String {
        if let token = ProcessInfo.processInfo.environment["BOB_TOKEN"], !token.isEmpty {
            return token
        }
        let path = NSString(string: "~/BOBAssistant/server/secrets/token").expandingTildeInPath
        return (try? String(contentsOfFile: path, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    private func apply(voice: Bool, theme: String, volume: Int, indicator: String) {
        colorful = indicator == "colorful"
        equalizerItem.state = colorful ? .on : .off
        plate.setColorful(colorful)
        volumeItems.forEach { $0.state = $0.tag == volume ? .on : .off }
        volumeItem.title = "Громкость голоса: \(volume)%"
        voiceOn = voice
        self.theme = theme
        voiceItem.state = voice ? .on : .off
        themeItem.state = theme == "light" ? .on : .off
        card.rerender(theme: Theme.named(theme))
    }

    @objc private func toggleVoice() {
        link.setVoice(!voiceOn)
    }

    @objc private func chooseVolume(_ sender: NSMenuItem) {
        link.setVolume(sender.tag)
    }

    @objc private func toggleEqualizer() {
        link.setIndicator(colorful ? "classic" : "colorful")
    }

    @objc private func toggleTheme() {
        link.setTheme(theme == "light" ? "dark" : "light")
    }

    @objc private func runDemo() {
        demoTimers.forEach { $0.invalidate() }
        demoTimers = []
        let request = "какая погода завтра в Москве"
        let answer = "Завтра в Москве от нуля до пяти градусов, мокрый снег."
        let words = request.split(separator: " ").map(String.init)
        var steps: [(Double, PlateState)] = [(0, PlateState(phase: "listening", request: "", answer: "", voice: voiceOn, theme: theme))]
        for index in 1...words.count {
            steps.append((0.9 + Double(index) * 0.4, PlateState(phase: "listening", request: words[0..<index].joined(separator: " "), answer: "", voice: voiceOn, theme: theme)))
        }
        let end = 0.9 + Double(words.count) * 0.4
        steps.append((end + 0.4, PlateState(phase: "thinking", request: request, answer: "", voice: voiceOn, theme: theme)))
        steps.append((end + 1.7, PlateState(phase: "answer", request: request, answer: answer, voice: voiceOn, theme: theme, window: 3.5)))
        steps.append((end + 6.2, PlateState(phase: "followup", request: request, answer: answer, voice: voiceOn, theme: theme, window: 3.5)))
        steps.append((end + 9.7, PlateState(phase: "idle", request: "", answer: "", voice: voiceOn, theme: theme)))
        for (delay, state) in steps {
            demoTimers.append(Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { [weak self] _ in
                self?.plate.render(state)
            })
        }
    }
}

let arguments = CommandLine.arguments
if arguments.count >= 2, arguments[1] == "--layout" {
    _ = NSApplication.shared
    let states: [(String, PlateState)] = [
        ("пусто", PlateState(phase: "listening", request: "", answer: "", voice: true)),
        ("слово", PlateState(phase: "listening", request: "какая", answer: "", voice: true)),
        ("фраза", PlateState(phase: "listening", request: "какая погода завтра в Москве", answer: "", voice: true)),
        ("длинно", PlateState(phase: "listening", request: "какая погода завтра в Москве и в Санкт-Петербурге и ещё в Белгороде и Курске", answer: "", voice: true)),
        ("думаю", PlateState(phase: "thinking", request: "какая погода завтра в Москве", answer: "", voice: true)),
        ("ответ", PlateState(phase: "answer", request: "какая погода завтра в Москве", answer: "Завтра в Москве от нуля до пяти градусов, мокрый снег.", voice: true))
    ]
    for (name, state) in states {
        let view = PlateView(frame: .zero)
        view.apply(state)
        let size = view.preferredSize()
        view.setFrameSize(size)
        view.layout()
        print("\(name.padding(toLength: 8, withPad: " ", startingAt: 0)) высота \(Int(size.height))  индикатор y=\(Int(view.indicatorFrame.minY)) центр=\(Int(view.indicatorFrame.midY))")
    }
    exit(0)
}
if arguments.count >= 5, arguments[1] == "--lamp-snapshot" {
    _ = NSApplication.shared
    let on = arguments[4] == "on"
    let view = LampView(frame: NSRect(origin: .zero, size: LampView.size))
    view.apply(LampState(name: "Лампа в спальне", on: on, red: 1, green: 0.1, blue: 0.15, brightness: 70), theme: Theme.named(arguments[3]))
    let canvas = NSView(frame: NSRect(x: 0, y: 0, width: LampView.size.width + 72, height: LampView.size.height + 72))
    canvas.wantsLayer = true
    canvas.layer?.backgroundColor = (arguments[3] == "light" ? NSColor(calibratedRed: 0.62, green: 0.76, blue: 0.9, alpha: 1) : NSColor(calibratedRed: 0.2, green: 0.3, blue: 0.15, alpha: 1)).cgColor
    view.frame.origin = NSPoint(x: 36, y: 36)
    canvas.addSubview(view)
    canvas.layoutSubtreeIfNeeded()
    if let bitmap = canvas.bitmapImageRepForCachingDisplay(in: canvas.bounds) {
        canvas.cacheDisplay(in: canvas.bounds, to: bitmap)
        try? bitmap.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: arguments[2]))
    }
    exit(0)
}
if arguments.count >= 4, arguments[1] == "--card-snapshot" {
    _ = NSApplication.shared
    let theme = Theme.named(arguments[3])
    let view = CardView(frame: NSRect(origin: .zero, size: CardView.size))
    view.apply(CardState(visible: true, title: "ЗМ", artist: "Whole Lotta Swag", cover: "https://avatars.yandex.net/get-music-content/175191/034e9c06.a.6119880-2/200x200", paused: arguments.count > 4), theme: theme)
    RunLoop.main.run(until: Date().addingTimeInterval(3))
    let canvas = NSView(frame: NSRect(x: 0, y: 0, width: CardView.size.width + 72, height: CardView.size.height + 72))
    canvas.wantsLayer = true
    canvas.layer?.backgroundColor = (arguments[3] == "light" ? NSColor(calibratedRed: 0.62, green: 0.76, blue: 0.9, alpha: 1) : NSColor(calibratedRed: 0.2, green: 0.3, blue: 0.15, alpha: 1)).cgColor
    view.frame.origin = NSPoint(x: 36, y: 36)
    canvas.addSubview(view)
    canvas.layoutSubtreeIfNeeded()
    if let bitmap = canvas.bitmapImageRepForCachingDisplay(in: canvas.bounds) {
        canvas.cacheDisplay(in: canvas.bounds, to: bitmap)
        try? bitmap.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: arguments[2]))
    }
    exit(0)
}
if arguments.count >= 3, arguments[1] == "--snapshots" {
    let directory = URL(fileURLWithPath: arguments[2])
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    _ = NSApplication.shared
    let request = "какая погода завтра в Москве"
    let answer = "Завтра в Москве от нуля до пяти градусов, мокрый снег."
    let backdrops: [String: [NSColor]] = [
        "dark": [NSColor(calibratedRed: 0.42, green: 0.56, blue: 0.23, alpha: 1), NSColor(calibratedRed: 0.1, green: 0.17, blue: 0.1, alpha: 1)],
        "light": [NSColor(calibratedRed: 0.62, green: 0.76, blue: 0.9, alpha: 1), NSColor(calibratedRed: 0.81, green: 0.85, blue: 0.89, alpha: 1)]
    ]
    for theme in ["dark", "light"] {
        let phases: [(String, PlateState)] = [
            ("listening", PlateState(phase: "listening", request: "какая погода завтра", answer: "", voice: true, theme: theme)),
            ("thinking", PlateState(phase: "thinking", request: request, answer: "", voice: true, theme: theme)),
            ("answer", PlateState(phase: "answer", request: request, answer: answer, voice: true, theme: theme)),
            ("followup", PlateState(phase: "followup", request: request, answer: answer, voice: true, theme: theme, window: 8)),
            ("long", PlateState(phase: "answer", request: "расскажи про Белгород", answer: "Белгород — город на юге России, административный центр одноимённой области. Он стоит на реке Северский Донец, в нём около трёхсот шестидесяти тысяч жителей.", voice: true, theme: theme))
        ]
        for (name, state) in phases {
            let view = PlateView(frame: .zero)
            view.apply(state)
            view.snapshot(to: directory.appendingPathComponent("\(theme)-\(name).png"), backdrop: backdrops[theme]!)
        }
    }
    exit(0)
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.accessory)
application.run()
