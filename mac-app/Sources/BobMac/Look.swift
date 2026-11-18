import AppKit

enum Look {
    static let glassTop = NSColor(calibratedRed: 52 / 255, green: 54 / 255, blue: 66 / 255, alpha: 245 / 255)
    static let glassBottom = NSColor(calibratedRed: 22 / 255, green: 23 / 255, blue: 30 / 255, alpha: 250 / 255)
    static let rim = NSColor(white: 1, alpha: 0.35)
    static let divider = NSColor(white: 1, alpha: 0.18)
    static let amber = [NSColor(calibratedRed: 1, green: 0.84, blue: 0.25, alpha: 1), NSColor(calibratedRed: 1, green: 0.59, blue: 0.16, alpha: 1)]
    static let green = [NSColor(calibratedRed: 0.47, green: 0.9, blue: 0.63, alpha: 1), NSColor(calibratedRed: 0.16, green: 0.7, blue: 0.43, alpha: 1)]

    static let corner: CGFloat = 22
    static let padH: CGFloat = 20
    static let padV: CGFloat = 13
    static let dot: CGFloat = 12
    static let dotGap: CGFloat = 11
    static let maxWidth: CGFloat = 520
    static let minWidth: CGFloat = 170
    static let ruleGap: CGFloat = 9
    static let hintGap: CGFloat = 6
    static let textSlack: CGFloat = 8

    static let requestFont = NSFont.systemFont(ofSize: 15)
    static let answerFont = NSFont.systemFont(ofSize: 17)
    static let hintFont = NSFont.systemFont(ofSize: 11)
    static let answerMaxLines = 5
    static let requestMaxLines = 2
}
