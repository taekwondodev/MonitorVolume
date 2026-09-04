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
    private let latencyRecorder: LatencyRecorder?

    init(latencyRecorder: LatencyRecorder? = nil) {
        self.latencyRecorder = latencyRecorder
    }

    isolated deinit {
        dismissTask?.cancel()
        panel?.close()
    }

    func show(
        _ state: ConfirmedMonitorState,
        interactionIDs: [ControlMeasurementID] = []
    ) {
        dismissTask?.cancel()

        let panel = panel ?? makePanel()
        latencyRecorder?.record(
            stage: .osdPresentationRequested,
            interactionIDs: interactionIDs
        )
        if let latencyRecorder {
            panel.contentView = MeasuredVolumeHostingView(
                rootView: VolumeOSDView(state: state)
            ) {
                latencyRecorder.record(
                    stage: .osdFirstDrawCompleted,
                    interactionIDs: interactionIDs
                )
            }
        } else {
            panel.contentView = NSHostingView(rootView: VolumeOSDView(state: state))
        }
        panel.setFrameOrigin(origin(for: panel.frame.size))
        panel.alphaValue = 1
        panel.orderFrontRegardless()
        self.panel = panel

        dismissTask = Task { [weak self, weak panel] in
            do {
                try await Task.sleep(for: .seconds(1))
            } catch {
                return
            }
            guard let self, let panel, self.panel === panel else {
                return
            }
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

@MainActor
private final class MeasuredVolumeHostingView: NSHostingView<VolumeOSDView> {
    private let onFirstDraw: @MainActor () -> Void
    private var hasRecordedFirstDraw = false

    required init(rootView: VolumeOSDView) {
        onFirstDraw = {}
        super.init(rootView: rootView)
    }

    init(rootView: VolumeOSDView, onFirstDraw: @escaping @MainActor () -> Void) {
        self.onFirstDraw = onFirstDraw
        super.init(rootView: rootView)
    }

    required init?(coder: NSCoder) {
        nil
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard !hasRecordedFirstDraw else {
            return
        }
        hasRecordedFirstDraw = true
        onFirstDraw()
    }
}