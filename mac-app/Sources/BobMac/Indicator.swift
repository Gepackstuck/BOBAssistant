import AppKit
import QuartzCore

final class Indicator: NSView {
    enum Mode { case bars, spin, breathe }

    private let glow = CAGradientLayer()
    private let orb = CAGradientLayer()
    private let bars = (0..<5).map { _ in CAGradientLayer() }
    private let heights: [CGFloat] = [10, 20, 13, 24, 11]
    private var mode: Mode?

    override var isFlipped: Bool { true }

    override init(frame: NSRect) {
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

        for bar in bars {
            bar.colors = [Look.barTop.cgColor, Look.barBottom.cgColor]
            bar.cornerRadius = 1.75
            layer?.addSublayer(bar)
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
        let width: CGFloat = 3.5
        let gap: CGFloat = 3
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
        for layer in [glow, orb] + bars {
            layer.removeAllAnimations()
        }
        let showOrb = next != .bars
        glow.isHidden = !showOrb
        orb.isHidden = !showOrb
        bars.forEach { $0.isHidden = showOrb }
        switch next {
        case .bars:
            for (index, bar) in bars.enumerated() {
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
        case .spin:
            let spin = CABasicAnimation(keyPath: "transform.rotation.z")
            spin.fromValue = 0
            spin.toValue = -2 * Double.pi
            spin.duration = 1.4
            spin.repeatCount = .infinity
            orb.add(spin, forKey: "spin")
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
