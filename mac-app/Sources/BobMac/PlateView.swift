import AppKit
import QuartzCore

struct PlateState: Equatable {
    var phase: String
    var request: String
    var answer: String
    var voice: Bool
    var theme: String = "dark"
    var window: Double = 0
}

final class PlateView: NSView {
    private let indicator = Indicator(frame: .zero)
    private let smallLabel = PlateView.label()
    private let bigLabel = PlateView.label()
    private let timerTrack = CALayer()
    private let timerFill = CAGradientLayer()
    private var state = PlateState(phase: "idle", request: "", answer: "", voice: true)
    private var theme = Theme.dark
    private var shownRequest = ""
    private var fadeTimer: Timer?

    override var isFlipped: Bool { true }

    var indicatorFrame: NSRect { indicator.frame }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer = CALayer()
        layer?.cornerRadius = Look.corner
        layer?.cornerCurve = .continuous
        layer?.masksToBounds = true
        layer?.borderWidth = 1

        timerFill.colors = [Look.accent[0].cgColor, Look.accent[1].cgColor, Look.accent[2].cgColor]
        timerFill.startPoint = CGPoint(x: 0, y: 0.5)
        timerFill.endPoint = CGPoint(x: 1, y: 0.5)
        timerFill.cornerRadius = Look.timerHeight / 2
        timerFill.anchorPoint = CGPoint(x: 0, y: 0.5)
        timerTrack.cornerRadius = Look.timerHeight / 2
        layer?.addSublayer(timerTrack)
        layer?.addSublayer(timerFill)

        smallLabel.font = Look.smallFont
        smallLabel.maximumNumberOfLines = 1
        bigLabel.font = Look.bigFont
        bigLabel.maximumNumberOfLines = Look.bigMaxLines
        [indicator, smallLabel, bigLabel].forEach { addSubview($0) }
    }

    required init?(coder: NSCoder) {
        fatalError()
    }

    private static func label() -> NSTextField {
        let field = NSTextField(labelWithString: "")
        field.lineBreakMode = .byWordWrapping
        field.cell?.wraps = true
        field.cell?.truncatesLastVisibleLine = true
        field.drawsBackground = false
        field.isBordered = false
        return field
    }

    private var listening: Bool { state.phase == "listening" }
    private var thinking: Bool { state.phase == "thinking" }
    private var showsTimer: Bool { state.phase == "followup" && state.window > 0 }

    private var smallText: String {
        if listening { return "Слушаю" }
        return state.request
    }

    private var bigText: String {
        if listening { return state.request.isEmpty ? "Говорите…" : state.request }
        if thinking { return "Думаю…" }
        return state.answer
    }

    private func height(of text: String, font: NSFont, width: CGFloat, lines: Int) -> CGFloat {
        guard !text.isEmpty else { return 0 }
        let rect = (text as NSString).boundingRect(
            with: NSSize(width: width - Look.slack, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading],
            attributes: [.font: font]
        )
        let line = ceil(font.ascender - font.descender + font.leading)
        return min(ceil(rect.height), line * CGFloat(lines))
    }

    private func width(of text: String, font: NSFont) -> CGFloat {
        ceil((text as NSString).size(withAttributes: [.font: font]).width) + Look.slack
    }

    private struct Measure {
        var small: CGFloat
        var big: CGFloat
        var block: CGFloat
        var total: CGFloat
    }

    func preferredSize() -> NSSize {
        let inner = Look.maxWidth - Look.padH * 2 - Look.indicator - Look.gap
        let content = min(max(width(of: smallText, font: Look.smallFont), width(of: bigText, font: Look.bigFont)), inner)
        let boxWidth = max(Look.minWidth, content + Look.indicator + Look.gap + Look.padH * 2)
        return NSSize(width: boxWidth, height: measure(boxWidth: boxWidth).total)
    }

    private func measure(boxWidth: CGFloat) -> Measure {
        let textWidth = boxWidth - Look.padH * 2 - Look.indicator - Look.gap
        let small = height(of: smallText, font: Look.smallFont, width: textWidth, lines: 1)
        let big = height(of: bigText, font: Look.bigFont, width: textWidth, lines: Look.bigMaxLines)
        let block = small + (small > 0 && big > 0 ? Look.lineGap : 0) + big
        let row = max(block, Look.indicator)
        let total = Look.padV * 2 + row
        return Measure(small: small, big: big, block: block, total: total)
    }

    override func layout() {
        super.layout()
        let layout = measure(boxWidth: bounds.width)
        let row = max(layout.block, Look.indicator)
        let top = Look.padV
        let lastLine = ceil(Look.bigFont.ascender - Look.bigFont.descender + Look.bigFont.leading)
        let center = top + row - lastLine / 2
        indicator.frame = NSRect(x: Look.padH, y: center - Look.indicator / 2, width: Look.indicator, height: Look.indicator)
        let textX = Look.padH + Look.indicator + Look.gap
        let textWidth = bounds.width - textX - Look.padH
        var y = top + (row - layout.block) / 2
        smallLabel.isHidden = layout.small == 0
        if layout.small > 0 {
            smallLabel.frame = NSRect(x: textX, y: y, width: textWidth, height: layout.small)
            y += layout.small + Look.lineGap
        }
        bigLabel.frame = NSRect(x: textX, y: y, width: textWidth, height: layout.big)
        let trackWidth = bounds.width - Look.padH * 2
        let trackY = bounds.height - Look.timerInset - Look.timerHeight
        timerTrack.frame = CGRect(x: Look.padH, y: trackY, width: trackWidth, height: Look.timerHeight)
        timerFill.bounds = CGRect(x: 0, y: 0, width: trackWidth, height: Look.timerHeight)
        timerFill.position = CGPoint(x: Look.padH, y: trackY + Look.timerHeight / 2)
        timerTrack.isHidden = !showsTimer
        timerFill.isHidden = !showsTimer
    }

    func apply(_ next: PlateState) {
        let previous = state
        state = next
        theme = Theme.named(next.theme)
        layer?.backgroundColor = theme.fill.cgColor
        layer?.borderColor = theme.rim.cgColor
        timerTrack.backgroundColor = theme.track.cgColor
        smallLabel.textColor = theme.secondary
        bigLabel.textColor = thinking || (listening && state.request.isEmpty) ? theme.secondary : theme.primary
        indicator.set(listening ? .bars : (thinking ? .spin : .breathe))
        applyTimer(previous: previous)
        smallLabel.stringValue = smallText
        setBig(bigText, previous: listening && !previous.request.isEmpty ? shownRequest : "")
        needsLayout = true
    }

    private func applyTimer(previous: PlateState) {
        guard showsTimer else {
            timerFill.removeAnimation(forKey: "timer")
            return
        }
        guard previous.phase != "followup" || timerFill.animation(forKey: "timer") == nil else { return }
        timerFill.removeAnimation(forKey: "timer")
        let animation = CABasicAnimation(keyPath: "transform.scale.x")
        animation.fromValue = 1.0
        animation.toValue = 0.0
        animation.duration = state.window
        animation.timingFunction = CAMediaTimingFunction(name: .linear)
        animation.fillMode = .forwards
        animation.isRemovedOnCompletion = false
        timerFill.add(animation, forKey: "timer")
    }

    private func setBig(_ text: String, previous: String) {
        fadeTimer?.invalidate()
        shownRequest = listening ? text : shownRequest
        guard listening, !previous.isEmpty, text.hasPrefix(previous), text.count > previous.count else {
            bigLabel.stringValue = text
            return
        }
        let split = previous.count
        let started = CACurrentMediaTime()
        let font = Look.bigFont
        let primary = theme.primary
        fadeTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] timer in
            guard let self else { timer.invalidate(); return }
            let progress = min(1, (CACurrentMediaTime() - started) / 0.26)
            let attributed = NSMutableAttributedString(string: text, attributes: [.font: font, .foregroundColor: primary])
            attributed.addAttribute(.foregroundColor, value: primary.withAlphaComponent(CGFloat(progress)), range: NSRange(location: split, length: text.count - split))
            self.bigLabel.attributedStringValue = attributed
            if progress >= 1 { timer.invalidate() }
        }
    }

    func snapshot(to url: URL, backdrop: [NSColor]) {
        let size = preferredSize()
        let margin: CGFloat = 36
        let canvas = Canvas(frame: NSRect(x: 0, y: 0, width: size.width + margin * 2, height: size.height + margin * 2), colors: backdrop)
        setFrameSize(size)
        frame.origin = NSPoint(x: margin, y: margin)
        canvas.addSubview(self)
        canvas.layoutSubtreeIfNeeded()
        layoutSubtreeIfNeeded()
        layout()
        let scale: CGFloat = 2
        guard let bitmap = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: Int(canvas.bounds.width * scale), pixelsHigh: Int(canvas.bounds.height * scale),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
        ) else { return }
        bitmap.size = canvas.bounds.size
        canvas.cacheDisplay(in: canvas.bounds, to: bitmap)
        if let data = bitmap.representation(using: .png, properties: [:]) {
            try? data.write(to: url)
        }
        removeFromSuperview()
    }
}

private final class Canvas: NSView {
    private let colors: [NSColor]

    init(frame: NSRect, colors: [NSColor]) {
        self.colors = colors
        super.init(frame: frame)
    }

    required init?(coder: NSCoder) {
        fatalError()
    }

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        NSGradient(colors: colors)?.draw(from: NSPoint(x: 0, y: 0), to: NSPoint(x: bounds.width, y: bounds.height), options: [])
    }
}
