import AppKit

struct Theme {
    let fill: NSColor
    let rim: NSColor
    let primary: NSColor
    let secondary: NSColor
    let track: NSColor

    static let dark = Theme(
        fill: NSColor(calibratedRed: 18 / 255, green: 19 / 255, blue: 24 / 255, alpha: 0.92),
        rim: NSColor(white: 1, alpha: 0.08),
        primary: .white,
        secondary: NSColor(white: 1, alpha: 0.52),
        track: NSColor(white: 1, alpha: 0.10)
    )
    static let light = Theme(
        fill: NSColor(white: 1, alpha: 0.9),
        rim: NSColor(white: 0, alpha: 0.06),
        primary: NSColor(calibratedRed: 21 / 255, green: 22 / 255, blue: 27 / 255, alpha: 1),
        secondary: NSColor(calibratedRed: 20 / 255, green: 22 / 255, blue: 30 / 255, alpha: 0.5),
        track: NSColor(white: 0, alpha: 0.08)
    )

    static func named(_ name: String) -> Theme {
        name == "light" ? light : dark
    }
}

enum Look {
    static let accent: [NSColor] = [
        NSColor(calibratedRed: 0.435, green: 0.659, blue: 1, alpha: 1),
        NSColor(calibratedRed: 0.71, green: 0.486, blue: 1, alpha: 1),
        NSColor(calibratedRed: 1, green: 0.498, blue: 0.714, alpha: 1),
        NSColor(calibratedRed: 1, green: 0.702, blue: 0.435, alpha: 1),
        NSColor(calibratedRed: 0.435, green: 0.659, blue: 1, alpha: 1)
    ]
    static let barTop = NSColor(calibratedRed: 0.545, green: 0.714, blue: 1, alpha: 1)
    static let barBottom = NSColor(calibratedRed: 0.773, green: 0.545, blue: 1, alpha: 1)

    static let corner: CGFloat = 26
    static let padH: CGFloat = 22
    static let padV: CGFloat = 20
    static let indicator: CGFloat = 26
    static let gap: CGFloat = 14
    static let maxWidth: CGFloat = 540
    static let minWidth: CGFloat = 240
    static let lineGap: CGFloat = 5
    static let timerHeight: CGFloat = 3
    static let timerInset: CGFloat = 9
    static let slack: CGFloat = 8
    static let smallFont = NSFont.systemFont(ofSize: 12.5)
    static let bigFont = NSFont.systemFont(ofSize: 18, weight: .semibold)
    static let bigMaxLines = 5
    static let reservedLines = 4
}
