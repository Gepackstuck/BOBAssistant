import AppKit

final class ServerManager {
    private let root = NSString(string: "~/BOBAssistant").expandingTildeInPath
    private var process: Process?
    private var stopping = false
    private var restarts = 0
    var onStatus: ((String) -> Void)?

    var logURL: URL { URL(fileURLWithPath: root + "/server/logs/server.out") }

    private func executable() -> (String, [String])? {
        let venv = root + "/server/.venv/bin/bob"
        if FileManager.default.isExecutableFile(atPath: venv) {
            return (venv, [])
        }
        for uv in ["/opt/homebrew/bin/uv", NSString("~/.local/bin/uv").expandingTildeInPath] where FileManager.default.isExecutableFile(atPath: uv) {
            return (uv, ["run", "bob"])
        }
        return nil
    }

    private func listeners() -> [Int32] {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        task.arguments = ["-nP", "-iTCP:8765", "-sTCP:LISTEN", "-t"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        guard (try? task.run()) != nil else { return [] }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        task.waitUntilExit()
        return (String(data: data, encoding: .utf8) ?? "").split(separator: "\n").compactMap { Int32($0) }
    }

    private func openLog() -> FileHandle? {
        let fm = FileManager.default
        try? fm.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let size = (try? fm.attributesOfItem(atPath: logURL.path))?[.size] as? Int, size > 5_000_000 {
            let old = logURL.appendingPathExtension("1")
            try? fm.removeItem(at: old)
            try? fm.moveItem(at: logURL, to: old)
        }
        if !fm.fileExists(atPath: logURL.path) {
            fm.createFile(atPath: logURL.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: logURL) else { return nil }
        handle.seekToEndOfFile()
        return handle
    }

    func start() {
        stopping = false
        guard process == nil else { return }
        if !listeners().isEmpty {
            onStatus?("Порт занят: жду, пока освободится или уже работает свой сервер")
            DispatchQueue.main.asyncAfter(deadline: .now() + 6) { [weak self] in
                guard let self, !self.stopping, self.process == nil else { return }
                self.start()
            }
            return
        }
        guard let (path, arguments) = executable() else {
            onStatus?("Не найден сервер Боба в ~/BOBAssistant/server")
            return
        }
        let task = Process()
        task.executableURL = URL(fileURLWithPath: path)
        task.arguments = arguments
        task.currentDirectoryURL = URL(fileURLWithPath: root + "/server")
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + (environment["PATH"] ?? "")
        task.environment = environment
        let log = openLog()
        task.standardOutput = log ?? FileHandle.nullDevice
        task.standardError = log ?? FileHandle.nullDevice
        task.terminationHandler = { [weak self] finished in
            DispatchQueue.main.async { self?.exited(finished) }
        }
        do {
            try task.run()
            process = task
            onStatus?("Сервер запускается…")
        } catch {
            onStatus?("Не удалось запустить сервер: \(error.localizedDescription)")
        }
    }

    private func exited(_ finished: Process) {
        if process === finished {
            process = nil
        }
        guard !stopping else { return }
        restarts += 1
        onStatus?("Сервер остановился, перезапускаю…")
        let delay = min(30.0, Double(restarts) * 3)
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in self?.start() }
    }

    func connected() {
        restarts = 0
    }

    func stop() {
        stopping = true
        process?.terminate()
        listeners().forEach { kill($0, SIGTERM) }
    }

    func restart() {
        onStatus?("Перезапускаю сервер…")
        stop()
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) { [weak self] in
            self?.process = nil
            self?.start()
        }
    }
}
