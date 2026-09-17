import AppKit
import SwiftUI

@MainActor
final class AccessibilityPermissionOverlayPanel: NSObject, AccessibilityPermissionOverlay {
    private enum Layout {
        static let size = NSSize(width: 530, height: 126)
        static let gap: CGFloat = 12
    }

    private let settings: any AccessibilitySettingsSession
    private var panel: NSPanel?
    private var trackingTimer: Timer?

    init(settings: any AccessibilitySettingsSession) {
        self.settings = settings
    }

    isolated deinit {
        trackingTimer?.invalidate()
        panel?.close()
    }

    func present(applicationURL: URL) {
        if panel == nil {
            let panel = makePanel()
            panel.contentView = NSHostingView(
                rootView: AccessibilityPermissionGuideView(applicationURL: applicationURL)
            )
            self.panel = panel
        }
        startTracking()
        refreshPosition()
    }

    func dismiss() {
        guard panel != nil || trackingTimer != nil else { return }
        trackingTimer?.invalidate()
        trackingTimer = nil
        panel?.orderOut(nil)
        panel?.close()
        panel = nil
    }

    @objc private func trackingTimerFired() {
        refreshPosition()
    }

    private func startTracking() {
        guard trackingTimer == nil else { return }
        trackingTimer = Timer.scheduledTimer(
            timeInterval: 0.15,
            target: self,
            selector: #selector(trackingTimerFired),
            userInfo: nil,
            repeats: true
        )
    }

    private func refreshPosition() {
        settings.refreshOwnership()
        guard let panel, let settingsFrame = settings.frontmostWindowFrame() else {
            panel?.orderOut(nil)
            return
        }
        guard let origin = adjacentOrigin(to: settingsFrame) else {
            panel.orderOut(nil)
            return
        }
        panel.setFrameOrigin(origin)
        panel.orderFrontRegardless()
    }

    private func adjacentOrigin(to settingsFrame: CGRect) -> NSPoint? {
        guard let visibleFrame = NSScreen.screens
            .map(\.visibleFrame)
            .filter({ $0.intersects(settingsFrame) })
            .max(by: {
                $0.intersection(settingsFrame).width * $0.intersection(settingsFrame).height
                    < $1.intersection(settingsFrame).width * $1.intersection(settingsFrame).height
            }) else {
            return nil
        }

        let centeredX = settingsFrame.midX - Layout.size.width / 2
        let centeredY = settingsFrame.midY - Layout.size.height / 2
        let candidates = [
            NSPoint(x: centeredX, y: settingsFrame.minY - Layout.gap - Layout.size.height),
            NSPoint(x: centeredX, y: settingsFrame.maxY + Layout.gap),
            NSPoint(x: settingsFrame.maxX + Layout.gap, y: centeredY),
            NSPoint(x: settingsFrame.minX - Layout.gap - Layout.size.width, y: centeredY),
        ]
        if let adjacent = candidates.first(where: { origin in
            visibleFrame.contains(NSRect(origin: origin, size: Layout.size))
        }) {
            return adjacent
        }
        guard visibleFrame.width >= Layout.size.width,
              visibleFrame.height >= Layout.size.height else {
            return nil
        }
        return NSPoint(
            x: min(max(centeredX, visibleFrame.minX), visibleFrame.maxX - Layout.size.width),
            y: min(
                max(settingsFrame.minY + Layout.gap, visibleFrame.minY),
                visibleFrame.maxY - Layout.size.height
            )
        )
    }

    private func makePanel() -> NSPanel {
        let panel = PermissionOverlayWindow(
            contentRect: NSRect(origin: .zero, size: Layout.size),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.backgroundColor = .clear
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.isMovable = false
        panel.isOpaque = false
        panel.level = .statusBar
        return panel
    }
}

private final class PermissionOverlayWindow: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

private struct AccessibilityPermissionGuideView: View {
    let applicationURL: URL

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: "arrow.up")
                    .font(.title2.bold())
                    .accessibilityHidden(true)
                Text("Drag Monitor Volume into the list above to allow Accessibility")
                    .font(.headline)
            }
            PermissionApplicationDragSource(applicationURL: applicationURL)
                .frame(height: 48)
        }
        .foregroundStyle(.white)
        .padding(18)
        .background(Color(red: 0.16, green: 0.16, blue: 0.16), in: RoundedRectangle(cornerRadius: 18))
        .overlay {
            RoundedRectangle(cornerRadius: 18)
                .stroke(.white.opacity(0.22), lineWidth: 1)
        }
        .padding(4)
    }
}

private struct PermissionApplicationDragSource: NSViewRepresentable {
    let applicationURL: URL

    func makeNSView(context: Context) -> PermissionApplicationDragView {
        PermissionApplicationDragView(applicationURL: applicationURL)
    }

    func updateNSView(_ nsView: PermissionApplicationDragView, context: Context) {}
}

private final class PermissionApplicationDragView: NSView, NSPasteboardItemDataProvider, NSDraggingSource {
    private let applicationURL: URL
    private let iconView: NSImageView
    private let titleField: NSTextField

    init(applicationURL: URL) {
        self.applicationURL = applicationURL
        iconView = NSImageView(image: NSWorkspace.shared.icon(forFile: applicationURL.path))
        titleField = NSTextField(labelWithString: "Monitor Volume")
        super.init(frame: .zero)
        configure()
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }

    override func mouseDown(with event: NSEvent) {
        let item = NSPasteboardItem()
        item.setDataProvider(self, forTypes: [.fileURL])
        let draggingItem = NSDraggingItem(pasteboardWriter: item)
        let iconFrame = iconView.convert(iconView.bounds, to: self)
        draggingItem.setDraggingFrame(iconFrame, contents: iconView.image)
        let session = beginDraggingSession(with: [draggingItem], event: event, source: self)
        session.animatesToStartingPositionsOnCancelOrFail = true
    }

    func pasteboard(
        _ pasteboard: NSPasteboard?,
        item: NSPasteboardItem,
        provideDataForType type: NSPasteboard.PasteboardType
    ) {
        guard type == .fileURL else { return }
        item.setData(applicationURL.dataRepresentation, forType: .fileURL)
    }

    func draggingSession(
        _ session: NSDraggingSession,
        sourceOperationMaskFor context: NSDraggingContext
    ) -> NSDragOperation {
        .copy
    }

    private func configure() {
        wantsLayer = true
        layer?.backgroundColor = NSColor.white.withAlphaComponent(0.08).cgColor
        layer?.borderColor = NSColor.white.withAlphaComponent(0.18).cgColor
        layer?.borderWidth = 1
        layer?.cornerRadius = 10

        iconView.imageScaling = .scaleProportionallyUpOrDown
        iconView.translatesAutoresizingMaskIntoConstraints = false
        addSubview(iconView)

        titleField.font = .systemFont(ofSize: NSFont.systemFontSize, weight: .semibold)
        titleField.textColor = .white
        titleField.translatesAutoresizingMaskIntoConstraints = false
        addSubview(titleField)

        NSLayoutConstraint.activate([
            iconView.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 10),
            iconView.centerYAnchor.constraint(equalTo: centerYAnchor),
            iconView.widthAnchor.constraint(equalToConstant: 32),
            iconView.heightAnchor.constraint(equalToConstant: 32),
            titleField.leadingAnchor.constraint(equalTo: iconView.trailingAnchor, constant: 10),
            titleField.trailingAnchor.constraint(lessThanOrEqualTo: trailingAnchor, constant: -10),
            titleField.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])

        setAccessibilityRole(.button)
        setAccessibilityLabel("Drag Monitor Volume to the Accessibility list")
        setAccessibilityHelp("Drag this item into the list above to grant Accessibility access")
    }
}
