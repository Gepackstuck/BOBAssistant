import AppKit
import QuartzCore

struct PlateState: Equatable {
    var phase: String
    var request: String
    var answer: String
    var voice: Bool
}

final class PlateView: NSView {
    private let gradient = CAGradientLayer()
    private let dotHolder = NSView()
    private let dotLayer = CAGradientLayer()
    private let requestLabel = PlateView.label()
    private let divider = NSView()
    private let answerLabel = PlateView.label()
    private let hintLabel = PlateView.label()
    private var state = PlateState(phase: "idle", request: "", answer: "", voice: true)
    private var shownRequest = ""
    private var fadeTimer: Timer?

    override var isFlipped: Bool { true }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer = CALayer()
        layer?.cornerRadius = Look.corner
        layer?.masksToBounds = true
        layer?.borderWidth = 1
        layer?.borderColor = Look.rim.cgColor
        gradient.colors = [Look.glassTop.cgColor, Look.glassBottom.cgColor]
        gradient.startPoint = CGPoint(x: 0.5, y: 1)
        gradient.endPoint = CGPoint(x: 0.5, y: 0)
        layer?.addSublayer(gradient)

        dotHolder.wantsLayer = true
        dotLayer.bounds = CGRect(x: 0, y: 0, width: Look.dot, height: Look.dot)
        dotLayer.cornerRadius = Look.dot / 2
        dotLayer.startPoint = CGPoint(x: 0.5, y: 1)
        dotLayer.endPoint = CGPoint(x: 0.5, y: 0)
        dotHolder.layer?.addSublayer(dotLayer)
        addSubview(dotHolder)

        requestLabel.font = Look.requestFont
        requestLabel.maximumNumberOfLines = Look.requestMaxLines
        answerLabel.font = Look.answerFont
        answerLabel.maximumNumberOfLines = Look.answerMaxLines
        hintLabel.font = Look.hintFont
        hintLabel.stringValue = "Можно уточнить…"
        hintLabel.textColor = NSColor(white: 1, alpha: 0.47)
        divider.wantsLayer = true
        divider.layer?.backgroundColor = Look.divider.cgColor
        [requestLabel, divider, answerLabel, hintLabel].forEach { addSubview($0) }
    }

    required init?(coder: NSCoder) {
        fatalError()
    }

    private static func label() -> NSTextField {
        let field = NSTextField(labelWithString: "")
        field.lineBreakMode = .byWordWrapping
        field.cell?.wraps = true
        field.cell?.truncatesLastVisibleLine = true
        field.textColor = .white
        field.drawsBackground = false
        field.isBordered = false
        return field
    }

    private var showsAnswer: Bool { state.phase == "answer" || state.phase == "followup" || state.phase == "thinking" }
    private var answerText: String { state.phase == "thinking" ? "Думаю…" : state.answer }
    private var requestText: String { state.request.isEmpty && state.phase == "listening" ? "Слушаю…" : state.request }

    private func height(of text: String, font: NSFont, width: CGFloat, lines: Int) -> CGFloat {
        guard !text.isEmpty else { return 0 }
        let rect = (text as NSString).boundingRect(
            with: NSSize(width: width - Look.textSlack, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading],
            attributes: [.font: font]
        )
        let line = ceil(font.ascender - font.descender + font.leading)
        return min(ceil(rect.height), line * CGFloat(lines))
    }

    private func width(of text: String, font: NSFont) -> CGFloat {
        ceil((text as NSString).size(withAttributes: [.font: font]).width) + Look.textSlack
    }

    func preferredSize() -> NSSize {
        let inner = Look.maxWidth - Look.padH * 2
        let requestWidth = width(of: requestText, font: Look.requestFont) + Look.dot + Look.dotGap
        let answerWidth = showsAnswer ? width(of: answerText, font: Look.answerFont) : 0
        let hintWidth = state.phase == "followup" ? width(of: hintLabel.stringValue, font: Look.hintFont) : 0
        let content = min(max(requestWidth, answerWidth, hintWidth), inner)
        let boxWidth = max(Look.minWidth, content + Look.padH * 2)
        let layout = measure(boxWidth: boxWidth)
        return NSSize(width: boxWidth, height: layout.total)
    }

    private struct Measure {
        var requestHeight: CGFloat
        var answerHeight: CGFloat
        var hintHeight: CGFloat
        var total: CGFloat
    }

    private func measure(boxWidth: CGFloat) -> Measure {
        let inner = boxWidth - Look.padH * 2
        let requestHeight = max(Look.dot, height(of: requestText, font: Look.requestFont, width: inner - Look.dot - Look.dotGap, lines: Look.requestMaxLines))
        let answerHeight = showsAnswer ? height(of: answerText, font: Look.answerFont, width: inner, lines: Look.answerMaxLines) : 0
        let hintHeight = state.phase == "followup" ? height(of: hintLabel.stringValue, font: Look.hintFont, width: inner, lines: 1) : 0
        var total = Look.padV * 2 + requestHeight
        if showsAnswer { total += Look.ruleGap * 2 + 1 + answerHeight }
        if hintHeight > 0 { total += Look.hintGap + hintHeight }
        return Measure(requestHeight: requestHeight, answerHeight: answerHeight, hintHeight: hintHeight, total: total)
    }

    override func layout() {
        super.layout()
        gradient.frame = bounds
        let inner = bounds.width - Look.padH * 2
        let layout = measure(boxWidth: bounds.width)
        var y = Look.padV
        dotHolder.frame = NSRect(x: Look.padH, y: y + (layout.requestHeight - Look.dot) / 2, width: Look.dot, height: Look.dot)
        dotLayer.position = CGPoint(x: Look.dot / 2, y: Look.dot / 2)
        let textX = Look.padH + Look.dot + Look.dotGap
        requestLabel.frame = NSRect(x: textX, y: y, width: inner - Look.dot - Look.dotGap, height: layout.requestHeight)
        y += layout.requestHeight
        divider.isHidden = !showsAnswer
        answerLabel.isHidden = !showsAnswer
        if showsAnswer {
            y += Look.ruleGap
            divider.frame = NSRect(x: Look.padH, y: y, width: inner, height: 1)
            y += 1 + Look.ruleGap
            answerLabel.frame = NSRect(x: Look.padH, y: y, width: inner, height: layout.answerHeight)
            y += layout.answerHeight
        }
        hintLabel.isHidden = layout.hintHeight == 0
        if layout.hintHeight > 0 {
            hintLabel.frame = NSRect(x: Look.padH, y: y + Look.hintGap, width: inner, height: layout.hintHeight)
        }
    }

    func apply(_ next: PlateState) {
        let previous = state
        state = next
        let colors = (next.phase == "followup" ? Look.green : Look.amber).map { $0.cgColor }
        dotLayer.colors = colors
        applyPulse(for: next.phase)
        answerLabel.stringValue = answerText
        answerLabel.textColor = .white
        requestLabel.alphaValue = showsAnswer && next.phase != "thinking" ? 0.66 : (next.request.isEmpty ? 0.6 : 1)
        answerLabel.alphaValue = next.phase == "thinking" ? 0.5 : 1
        setRequest(requestText, previous: previous.request.isEmpty ? "" : shownRequest)
        needsLayout = true
    }

    private func applyPulse(for phase: String) {
        dotLayer.removeAnimation(forKey: "pulse")
        let strength: CGFloat = phase == "listening" ? 0.35 : (phase == "thinking" ? 0.18 : 0)
        guard strength > 0 else { return }
        let animation = CABasicAnimation(keyPath: "transform.scale")
        animation.fromValue = 1.0
        animation.toValue = 1.0 + strength
        animation.duration = 0.9
        animation.autoreverses = true
        animation.repeatCount = .infinity
        animation.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        dotLayer.add(animation, forKey: "pulse")
    }

    private func setRequest(_ text: String, previous: String) {
        fadeTimer?.invalidate()
        shownRequest = text
        guard !previous.isEmpty, text.hasPrefix(previous), text.count > previous.count else {
            requestLabel.stringValue = text
            return
        }
        let split = previous.count
        let started = CACurrentMediaTime()
        fadeTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] timer in
            guard let self else { timer.invalidate(); return }
            let progress = min(1, (CACurrentMediaTime() - started) / 0.26)
            let attributed = NSMutableAttributedString(string: text, attributes: [.font: Look.requestFont, .foregroundColor: NSColor.white])
            let range = NSRange(location: split, length: text.count - split)
            attributed.addAttribute(.foregroundColor, value: NSColor(white: 1, alpha: CGFloat(progress)), range: range)
            self.requestLabel.attributedStringValue = attributed
            if progress >= 1 { timer.invalidate() }
        }
    }

    func snapshot(to url: URL) {
        let size = preferredSize()
        setFrameSize(size)
        layoutSubtreeIfNeeded()
        layout()
        let scale: CGFloat = 2
        guard let bitmap = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: Int(size.width * scale), pixelsHigh: Int(size.height * scale),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
        ) else { return }
        bitmap.size = size
        guard let context = NSGraphicsContext(bitmapImageRep: bitmap) else { return }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
        let background = NSBezierPath(roundedRect: NSRect(origin: .zero, size: size), xRadius: Look.corner, yRadius: Look.corner)
        background.addClip()
        NSGradient(starting: Look.glassTop, ending: Look.glassBottom)?.draw(in: NSRect(origin: .zero, size: size), angle: 270)
        cacheDisplay(in: bounds, to: bitmap)
        NSGraphicsContext.restoreGraphicsState()
        if let data = bitmap.representation(using: .png, properties: [:]) {
            try? data.write(to: url)
        }
    }
}
