import AppKit
import QuartzCore

final class Indicator: NSView {
    enum Mode { case bars, spin, breathe, speak, idle }

    private let glow = CAGradientLayer()
    private let orb = CAGradientLayer()
    private let bars = (0..<5).map { _ in CAGradientLayer() }
    private let ripples = (0..<2).map { _ in CAShapeLayer() }
    private(set) var colorful: Bool
    private var heights: [CGFloat] { colorful ? [13, 21, 26, 19, 14] : [10, 20, 13, 24, 11] }
    private let rhythm: [[Double]] = [
        [0.45, 1.0, 0.6, 0.9, 0.5, 0.8, 0.45],
        [1.0, 0.5, 0.9, 0.4, 0.85, 0.55, 1.0],
        [0.6, 0.9, 0.45, 1.0, 0.7, 0.4, 0.6],
        [0.9, 0.45, 0.8, 0.6, 1.0, 0.5, 0.9],
        [0.5, 0.85, 0.55, 0.95, 0.4, 0.9, 0.5]
    ]
    private let durations: [Double] = [1.05, 0.9, 1.2, 0.95, 1.1]
    private var mode: Mode?

    override var isFlipped: Bool { true }

    init(frame: NSRect, colorful: Bool = false) {
        self.colorful = colorful
        super.init(frame: frame)
        wantsLayer = true
        layer = CALayer()
        layer?.masksToBounds = false

        glow.type = .radial
        glow.colors = [Look.accent[1].withAlphaComponent(0.5).cgColor, Look.accent[1].withAlphaComponent(0).cgColor]
        glow.startPoint = CGPoint(x: 0.5, y: 0.5)
        glow.endPoint = CGPoint(x: 1, y: 1)
        glow.bounds = CGRect(x: 0, y: 0, width: Look.indicator * 2.3, height: Look.indicator * 2.3)
        layer?.addSublayer(glow)

        orb.type = .conic
        orb.colors = Look.accent.map { $0.cgColor }
        orb.startPoint = CGPoint(x: 0.5, y: 0.5)
        orb.endPoint = CGPoint(x: 0.5, y: 0)
        orb.bounds = CGRect(x: 0, y: 0, width: Look.indicator, height: Look.indicator)
        let mask = CAShapeLayer()
        mask.path = CGPath(ellipseIn: orb.bounds, transform: nil)
        orb.mask = mask
        layer?.addSublayer(orb)

        for (index, ring) in ripples.enumerated() {
            ring.bounds = CGRect(x: 0, y: 0, width: Look.indicator, height: Look.indicator)
            ring.path = CGPath(ellipseIn: ring.bounds, transform: nil)
            ring.fillColor = nil
            ring.strokeColor = Look.accent[index == 0 ? 0 : 2].cgColor
            ring.lineWidth = 1.5
            ring.isHidden = true
            layer?.insertSublayer(ring, below: orb)
        }
        bars.forEach { layer?.addSublayer($0) }
        paint()
    }

    private func paint() {
        for (index, bar) in bars.enumerated() {
            bar.colors = colorful ? [Look.accent[index % 4].cgColor, Look.accent[(index + 1) % 4].cgColor] : [Look.barTop.cgColor, Look.barBottom.cgColor]
            bar.cornerRadius = colorful ? 2 : 1.75
        }
    }

    func setColorful(_ value: Bool) {
        guard value != colorful else { return }
        colorful = value
        paint()
        needsLayout = true
        let current = mode
        mode = nil
        if let current {
            set(current)
        }
    }

    required init?(coder: NSCoder) {
        fatalError()
    }

    override func layout() {
        super.layout()
        let center = CGPoint(x: bounds.midX, y: bounds.midY)
        glow.position = center
        orb.position = center
        ripples.forEach { $0.position = center }
        let width: CGFloat = colorful ? 4 : 3.5
        let gap: CGFloat = colorful ? 2.5 : 3
        let total = CGFloat(bars.count) * width + CGFloat(bars.count - 1) * gap
        for (index, bar) in bars.enumerated() {
            let height = heights[index] * Look.indicator / 26
            bar.bounds = CGRect(x: 0, y: 0, width: width, height: height)
            bar.position = CGPoint(x: bounds.midX - total / 2 + width / 2 + CGFloat(index) * (width + gap), y: bounds.midY)
        }
    }

    func set(_ next: Mode) {
        guard next != mode else { return }
        mode = next
        for layer in [glow, orb] + bars + ripples {
            layer.removeAllAnimations()
        }
        let showOrb = next != .bars && next != .idle
        glow.isHidden = !showOrb
        orb.isHidden = !showOrb
        ripples.forEach { $0.isHidden = next != .speak }
        bars.forEach { $0.isHidden = next != .bars }
        switch next {
        case .bars:
            for (index, bar) in bars.enumerated() {
                if colorful {
                    let animation = CAKeyframeAnimation(keyPath: "transform.scale.y")
                    animation.values = rhythm[index]
                    animation.duration = durations[index]
                    animation.calculationMode = .cubic
                    animation.repeatCount = .infinity
                    animation.timeOffset = Double(index) * 0.11
                    bar.add(animation, forKey: "bar")
                } else {
                    let animation = CABasicAnimation(keyPath: "transform.scale.y")
                    animation.fromValue = 1.0
                    animation.toValue = 0.4
                    animation.duration = 0.45
                    animation.autoreverses = true
                    animation.repeatCount = .infinity
                    animation.timeOffset = Double(index) * 0.13
                    animation.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                    bar.add(animation, forKey: "bar")
                }
            }
        case .spin:
            let spin = CABasicAnimation(keyPath: "transform.rotation.z")
            spin.fromValue = 0
            spin.toValue = -2 * Double.pi
            spin.duration = 1.4
            spin.repeatCount = .infinity
            orb.add(spin, forKey: "spin")
        case .speak:
            let spin = CABasicAnimation(keyPath: "transform.rotation.z")
            spin.fromValue = 0
            spin.toValue = -2 * Double.pi
            spin.duration = 3.2
            spin.repeatCount = .infinity
            orb.add(spin, forKey: "spin")
            let pulse = CABasicAnimation(keyPath: "transform.scale")
            pulse.fromValue = 0.9
            pulse.toValue = 1.45
            pulse.duration = 0.7
            pulse.autoreverses = true
            pulse.repeatCount = .infinity
            pulse.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            glow.add(pulse, forKey: "speak")
            for (index, ring) in ripples.enumerated() {
                let grow = CABasicAnimation(keyPath: "transform.scale")
                grow.fromValue = 1.0
                grow.toValue = 2.2
                let fade = CABasicAnimation(keyPath: "opacity")
                fade.fromValue = 0.75
                fade.toValue = 0.0
                let group = CAAnimationGroup()
                group.animations = [grow, fade]
                group.duration = 1.5
                group.repeatCount = .infinity
                group.timeOffset = Double(index) * 0.75
                group.timingFunction = CAMediaTimingFunction(name: .easeOut)
                ring.add(group, forKey: "ripple")
            }
        case .idle:
            break
        case .breathe:
            let pulse = CABasicAnimation(keyPath: "transform.scale")
            pulse.fromValue = 1.0
            pulse.toValue = 1.14
            pulse.duration = 1.5
            pulse.autoreverses = true
            pulse.repeatCount = .infinity
            pulse.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            orb.add(pulse, forKey: "breathe")
            glow.add(pulse, forKey: "breathe")
        }
    }
}
