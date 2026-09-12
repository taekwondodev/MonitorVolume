import AppKit
import ProArtVolumeCore
import SwiftUI

@MainActor
final class VolumeOSDPresenter {
    private enum Layout {
        static let size = NSSize(width: 360, height: 118)
        static let topInset: CGFloat = 24
    }

    private var panel: NSPanel?
    private var dismissTask: Task<Void, Never>?
    private var pulseTask: Task<Void, Never>?
    private var presentationRevision: UInt64 = 0

    isolated deinit {
        dismissTask?.cancel()
        pulseTask?.cancel()
        panel?.close()
    }

    func show(_ state: VolumeIntent, displayName: String, boundary: Bool) {
        dismissTask?.cancel()
        pulseTask?.cancel()
        presentationRevision += 1
        let revision = presentationRevision
        let entering = panel == nil

        let panel = panel ?? makePanel()
        let root = VolumeOSDView(state: state, displayName: displayName, entered: !entering, pulse: boundary)
        if let hosting = panel.contentView as? NSHostingView<VolumeOSDView> {
            hosting.rootView = root
        } else {
            panel.contentView = NSHostingView(rootView: root)
        }
        if entering {
            panel.setFrameOrigin(origin(for: panel.frame.size))
            panel.alphaValue = 0
        }
        panel.orderFrontRegardless()
        self.panel = panel

        if entering || panel.alphaValue < 1 {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.12
                panel.animator().alphaValue = 1
            }
        }
        pulseTask = Task { [weak self, weak panel] in
            await Task.yield()
            guard let self, let panel, presentationRevision == revision,
                  let hosting = panel.contentView as? NSHostingView<VolumeOSDView> else { return }
            hosting.rootView.entered = true
            do { try await Task.sleep(for: .milliseconds(100)) } catch { return }
            guard presentationRevision == revision else { return }
            hosting.rootView.pulse = false
            pulseTask = nil
        }

        dismissTask = Task { [weak self, weak panel] in
            do {
                try await Task.sleep(for: .seconds(1))
            } catch {
                return
            }
            guard let self, let panel, self.panel === panel else {
                return
            }
            await NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.22
                panel.animator().alphaValue = 0
            }
            guard !Task.isCancelled, self.presentationRevision == revision else { return }
            panel.orderOut(nil)
            self.panel = nil
            dismissTask = nil
        }
    }

    private func makePanel() -> NSPanel {
        let panel = NSPanel(
            contentRect: NSRect(origin: .zero, size: Layout.size),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.backgroundColor = .clear
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.ignoresMouseEvents = true
        panel.isMovable = false
        panel.isOpaque = false
        panel.level = .statusBar
        return panel
    }

    private func origin(for size: NSSize) -> NSPoint {
        let screen = NSScreen.screens.first { $0.frame.contains(NSEvent.mouseLocation) } ?? NSScreen.main
        guard let visibleFrame = screen?.visibleFrame else {
            return .zero
        }
        return NSPoint(
            x: visibleFrame.midX - size.width / 2,
            y: visibleFrame.maxY - size.height - Layout.topInset
        )
    }
}

