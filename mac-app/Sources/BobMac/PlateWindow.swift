import AppKit

final class PlateWindow {
    private let panel: NSPanel
    private let view = PlateView(frame: .zero)
    private var visible = false
    private var failsafe: DispatchWorkItem?

    init() {
        panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
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

    func render(_ state: PlateState) {
        failsafe?.cancel()
        if state.phase == "idle" {
            hide()
            return
        }
        let task = DispatchWorkItem { [weak self] in self?.hide() }
        failsafe = task
        DispatchQueue.main.asyncAfter(deadline: .now() + 30, execute: task)
        view.apply(state)
        let size = view.preferredSize()
        let frame = target(for: size)
        if visible {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.18
                context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                panel.animator().setFrame(frame, display: true)
            }
        } else {
            visible = true
            panel.setFrame(frame.offsetBy(dx: 0, dy: -14), display: false)
            panel.orderFrontRegardless()
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.22
                context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                panel.animator().alphaValue = 1
                panel.animator().setFrame(frame, display: true)
            }
        }
    }

    private func target(for size: NSSize) -> NSRect {
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let top = screen.minY + 24 + view.reservedHeight()
        return NSRect(x: screen.midX - size.width / 2, y: max(screen.minY + 16, top - size.height), width: size.width, height: size.height)
    }

    private func hide() {
        failsafe?.cancel()
        guard visible else { return }
        visible = false
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.26
            panel.animator().alphaValue = 0
        }, completionHandler: { [weak self] in
            guard let self, !self.visible else { return }
            self.panel.orderOut(nil)
        })
    }
}
