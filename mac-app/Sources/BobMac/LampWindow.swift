import AppKit

struct LampState: Equatable {
    var name: String
    var on: Bool
    var red: Double
    var green: Double
    var blue: Double
    var brightness: Int
    var pending: Bool = false
}

final class LampView: NSView {
    static let size = NSSize(width: 300, height: 76)
    private let bulb = NSImageView()
    private let titleLabel = NSTextField(labelWithString: "")
    private let stateLabel = NSTextField(labelWithString: "")
    private let glow = CAGradientLayer()

    override var isFlipped: Bool { true }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer = CALayer()
        layer?.cornerRadius = 20
        layer?.cornerCurve = .continuous
        layer?.masksToBounds = true
        layer?.borderWidth = 1

        glow.type = .radial
        glow.startPoint = CGPoint(x: 0.5, y: 0.5)
        glow.endPoint = CGPoint(x: 1, y: 1)
        glow.frame = CGRect(x: -6, y: -6, width: 100, height: 100)
        layer?.addSublayer(glow)

        bulb.frame = NSRect(x: 18, y: 14, width: 48, height: 48)
        bulb.imageScaling = .scaleProportionallyUpOrDown
        titleLabel.font = NSFont.systemFont(ofSize: 14, weight: .semibold)
        stateLabel.font = NSFont.systemFont(ofSize: 12.5)
        [titleLabel, stateLabel].forEach {
            $0.lineBreakMode = .byTruncatingTail
            $0.maximumNumberOfLines = 1
            $0.drawsBackground = false
            $0.isBordered = false
        }
        titleLabel.frame = NSRect(x: 82, y: 17, width: 200, height: 19)
        stateLabel.frame = NSRect(x: 82, y: 40, width: 200, height: 17)
        [bulb, titleLabel, stateLabel].forEach { addSubview($0) }
    }

    required init?(coder: NSCoder) {
        fatalError()
    }

    func apply(_ state: LampState, theme: Theme) {
        layer?.backgroundColor = theme.fill.cgColor
        layer?.borderColor = theme.rim.cgColor
        titleLabel.textColor = theme.primary
        stateLabel.textColor = theme.secondary
        titleLabel.stringValue = state.name
        stateLabel.stringValue = state.pending ? "Жду ответа лампы…" : (state.on ? "Включена, \(state.brightness)%" : "Выключена")
        let color = NSColor(calibratedRed: state.red, green: state.green, blue: state.blue, alpha: 1)
        glow.colors = state.on
            ? [color.withAlphaComponent(0.55).cgColor, color.withAlphaComponent(0).cgColor]
            : [NSColor.clear.cgColor, NSColor.clear.cgColor]
        let symbol = NSImage(systemSymbolName: state.on ? "lightbulb.fill" : "lightbulb", accessibilityDescription: state.name)
        bulb.image = symbol?.withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize: 34, weight: .regular))
        bulb.contentTintColor = state.on ? color : theme.secondary
    }
}

final class LampWindow {
    private let panel: NSPanel
    private let view = LampView(frame: NSRect(origin: .zero, size: LampView.size))
    private var shown = false
    private var hideTask: DispatchWorkItem?

    init() {
        panel = NSPanel(contentRect: NSRect(origin: .zero, size: LampView.size), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.level = .statusBar
        panel.ignoresMouseEvents = true
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panel.contentView = view
        panel.alphaValue = 0
    }

    func render(_ state: LampState, theme: Theme) {
        view.apply(state, theme: theme)
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let frame = NSRect(x: screen.minX + 24, y: screen.minY + 24, width: LampView.size.width, height: LampView.size.height)
        if !shown {
            shown = true
            panel.setFrame(frame.offsetBy(dx: 0, dy: -10), display: false)
            panel.orderFrontRegardless()
        }
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.22
            panel.animator().alphaValue = 1
            panel.animator().setFrame(frame, display: true)
        }
        hideTask?.cancel()
        let task = DispatchWorkItem { [weak self] in self?.hide() }
        hideTask = task
        DispatchQueue.main.asyncAfter(deadline: .now() + 6, execute: task)
    }

    func hide() {
        guard shown else { return }
        shown = false
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.3
            panel.animator().alphaValue = 0
        }, completionHandler: { [weak self] in
            guard let self, !self.shown else { return }
            self.panel.orderOut(nil)
        })
    }
}
