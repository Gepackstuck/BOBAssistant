import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let plate = PlateWindow()
    private var statusItem: NSStatusItem!
    private var link: Link!
    private let statusLine = NSMenuItem(title: "Нет связи с Бобом", action: nil, keyEquivalent: "")
    private let voiceItem = NSMenuItem(title: "Отвечать голосом", action: #selector(toggleVoice), keyEquivalent: "")
    private var voiceOn = true
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
        link.onSettings = { [weak self] voice in self?.setVoice(voice) }
        link.onConnection = { [weak self] connected in
            self?.statusLine.title = connected ? "Подключено к Бобу" : "Нет связи с Бобом"
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

    private func setVoice(_ enabled: Bool) {
        voiceOn = enabled
        voiceItem.state = enabled ? .on : .off
    }

    @objc private func toggleVoice() {
        link.setVoice(!voiceOn)
    }

    @objc private func runDemo() {
        demoTimers.forEach { $0.invalidate() }
        demoTimers = []
        let request = "какая погода завтра в Москве"
        let answer = "Завтра в Москве от нуля до пяти градусов, мокрый снег."
        let words = request.split(separator: " ").map(String.init)
        var steps: [(Double, PlateState)] = [(0, PlateState(phase: "listening", request: "", answer: "", voice: voiceOn))]
        for index in 1...words.count {
            steps.append((0.9 + Double(index) * 0.4, PlateState(phase: "listening", request: words[0..<index].joined(separator: " "), answer: "", voice: voiceOn)))
        }
        let end = 0.9 + Double(words.count) * 0.4
        steps.append((end + 0.4, PlateState(phase: "thinking", request: request, answer: "", voice: voiceOn)))
        steps.append((end + 1.7, PlateState(phase: "answer", request: request, answer: answer, voice: voiceOn)))
        steps.append((end + 6.2, PlateState(phase: "followup", request: request, answer: answer, voice: voiceOn)))
        steps.append((end + 9.7, PlateState(phase: "idle", request: "", answer: "", voice: voiceOn)))
        for (delay, state) in steps {
            demoTimers.append(Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { [weak self] _ in
                self?.plate.render(state)
            })
        }
    }
}

let arguments = CommandLine.arguments
if arguments.count >= 3, arguments[1] == "--snapshots" {
    let directory = URL(fileURLWithPath: arguments[2])
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    _ = NSApplication.shared
    let request = "какая погода завтра в Москве"
    let answer = "Завтра в Москве от нуля до пяти градусов, мокрый снег."
    let phases: [(String, PlateState)] = [
        ("1-listening-start", PlateState(phase: "listening", request: "", answer: "", voice: true)),
        ("2-listening-words", PlateState(phase: "listening", request: "какая погода завтра", answer: "", voice: true)),
        ("3-thinking", PlateState(phase: "thinking", request: request, answer: "", voice: true)),
        ("4-answer", PlateState(phase: "answer", request: request, answer: answer, voice: true)),
        ("5-followup", PlateState(phase: "followup", request: request, answer: answer, voice: true)),
        ("6-long-answer", PlateState(phase: "answer", request: "расскажи про Белгород", answer: "Белгород — город на юге России, административный центр одноимённой области. Он стоит на реке Северский Донец, в нём около трёхсот шестидесяти тысяч жителей, и это один из центров Центрально-Чернозёмного района.", voice: true))
    ]
    for (name, state) in phases {
        let view = PlateView(frame: .zero)
        view.apply(state)
        view.snapshot(to: directory.appendingPathComponent("\(name).png"))
    }
    exit(0)
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.accessory)
application.run()
