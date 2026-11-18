import AppKit

struct CardState: Equatable {
    var visible: Bool
    var title: String = ""
    var artist: String = ""
    var cover: String = ""
    var paused: Bool = false
}

final class CardView: NSView {
    static let size = NSSize(width: 320, height: 76)
    private static var cache: [String: NSImage] = [:]
    private let coverView = NSImageView()
    private let titleLabel = NSTextField(labelWithString: "")
    private let artistLabel = NSTextField(labelWithString: "")
    private let pauseView = NSImageView()
    private let equalizer = Indicator(frame: NSRect(x: 0, y: 0, width: Look.indicator, height: Look.indicator), colorful: true)
    private var cover = ""

    override var isFlipped: Bool { true }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer = CALayer()
        layer?.cornerRadius = 20
        layer?.cornerCurve = .continuous
        layer?.masksToBounds = true
        layer?.borderWidth = 1

        coverView.imageScaling = .scaleAxesIndependently
        coverView.wantsLayer = true
        coverView.layer?.cornerRadius = 12
        coverView.layer?.cornerCurve = .continuous
        coverView.layer?.masksToBounds = true
        coverView.layer?.backgroundColor = NSColor(white: 0.5, alpha: 0.25).cgColor
        coverView.frame = NSRect(x: 12, y: 12, width: 52, height: 52)

        titleLabel.font = NSFont.systemFont(ofSize: 14, weight: .semibold)
        artistLabel.font = NSFont.systemFont(ofSize: 12.5)
        [titleLabel, artistLabel].forEach {
            $0.lineBreakMode = .byTruncatingTail
            $0.maximumNumberOfLines = 1
            $0.drawsBackground = false
            $0.isBordered = false
        }
        titleLabel.frame = NSRect(x: 76, y: 17, width: 190, height: 19)
        artistLabel.frame = NSRect(x: 76, y: 40, width: 190, height: 17)

        pauseView.image = NSImage(systemSymbolName: "pause.fill", accessibilityDescription: "Пауза")
        pauseView.frame = NSRect(x: Self.size.width - 12 - 22, y: 27, width: 22, height: 22)
        pauseView.isHidden = true
        equalizer.frame = NSRect(x: Self.size.width - 12 - Look.indicator - 2, y: (Self.size.height - Look.indicator) / 2, width: Look.indicator, height: Look.indicator)
        [coverView, titleLabel, artistLabel, pauseView, equalizer].forEach { addSubview($0) }
    }

    required init?(coder: NSCoder) {
        fatalError()
    }

    func apply(_ state: CardState, theme: Theme) {
        layer?.backgroundColor = theme.fill.cgColor
        layer?.borderColor = theme.rim.cgColor
        titleLabel.textColor = theme.primary
        artistLabel.textColor = theme.secondary
        pauseView.contentTintColor = theme.secondary
        pauseView.isHidden = !state.paused
        equalizer.isHidden = state.paused
        equalizer.set(state.paused ? .idle : .bars)
        titleLabel.stringValue = state.title
        artistLabel.stringValue = state.artist
        let width: CGFloat = 190
        titleLabel.frame.size.width = width
        artistLabel.frame.size.width = width
        guard state.cover != cover else { return }
        cover = state.cover
        if let cached = Self.cache[state.cover] {
            coverView.image = cached
            return
        }
        coverView.image = nil
        guard let url = URL(string: state.cover), !state.cover.isEmpty else { return }
        URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
            guard let data, let image = NSImage(data: data) else { return }
            DispatchQueue.main.async {
                Self.cache[url.absoluteString] = image
                if self?.cover == url.absoluteString {
                    self?.coverView.image = image
                }
            }
        }.resume()
    }
}

final class CardWindow {
    private let panel: NSPanel
    private let view = CardView(frame: NSRect(origin: .zero, size: CardView.size))
    private var shown = false
    private var last = CardState(visible: false)

    init() {
        panel = NSPanel(contentRect: NSRect(origin: .zero, size: CardView.size), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
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

    func render(_ state: CardState, theme: Theme) {
        last = state
        guard state.visible else {
            hide()
            return
        }
        view.apply(state, theme: theme)
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let frame = NSRect(x: screen.maxX - CardView.size.width - 24, y: screen.minY + 24, width: CardView.size.width, height: CardView.size.height)
        if !shown {
            shown = true
            panel.setFrame(frame.offsetBy(dx: 0, dy: -10), display: false)
            panel.orderFrontRegardless()
        }
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.22
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            panel.animator().alphaValue = 1
            panel.animator().setFrame(frame, display: true)
        }
    }

    func rerender(theme: Theme) {
        if last.visible {
            render(last, theme: theme)
        }
    }

    func hide() {
        guard shown else { return }
        shown = false
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.26
            panel.animator().alphaValue = 0
        }, completionHandler: { [weak self] in
            guard let self, !self.shown else { return }
            self.panel.orderOut(nil)
        })
    }
}
