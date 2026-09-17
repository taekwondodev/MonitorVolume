import Foundation

@MainActor
protocol AccessibilityTrustChecking: AnyObject {
    var isGranted: Bool { get }
}

@MainActor
protocol AccessibilitySettingsSession: AnyObject {
    func openAccessibility()
    func refreshOwnership()
    func closeOwnedWindow()
    func frontmostWindowFrame() -> CGRect?
}

@MainActor
protocol AccessibilityPermissionOverlay: AnyObject {
    func present(applicationURL: URL)
    func dismiss()
}

enum AccessibilityPermissionBeginResult: Equatable {
    case alreadyGranted
    case waitingForGrant
}

enum AccessibilityPermissionEndReason: Equatable {
    case sleep
    case termination
    case superseded
    case deinitialization
}

@MainActor
final class AccessibilityPermissionSession {
    private enum Presentation: Equatable {
        case guided
        case silent
    }

    private struct Waiting {
        let generation: UInt64
        let presentation: Presentation
        let pollTask: Task<Void, Never>
    }

    private enum State {
        case idle
        case waiting(Waiting)
        case granted(generation: UInt64)
        case ended(generation: UInt64?, reason: AccessibilityPermissionEndReason)
    }

    private let applicationURL: URL
    private let trust: any AccessibilityTrustChecking
    private let settings: any AccessibilitySettingsSession
    private let overlay: any AccessibilityPermissionOverlay
    private var onGranted: @MainActor (UInt64) -> Void
    private var state = State.idle

    init(
        applicationURL: URL,
        trust: any AccessibilityTrustChecking,
        settings: any AccessibilitySettingsSession,
        overlay: any AccessibilityPermissionOverlay,
        onGranted: @escaping @MainActor (UInt64) -> Void
    ) {
        self.applicationURL = applicationURL
        self.trust = trust
        self.settings = settings
        self.overlay = overlay
        self.onGranted = onGranted
    }

    func setGrantHandler(_ handler: @escaping @MainActor (UInt64) -> Void) {
        onGranted = handler
    }

    isolated deinit {
        if case let .waiting(waiting) = state {
            waiting.pollTask.cancel()
        }
    }

    func beginGuided(for generation: UInt64) -> AccessibilityPermissionBeginResult {
        guard !trust.isGranted else {
            completeWithoutCallback(generation: generation)
            return .alreadyGranted
        }

        switch state {
        case let .waiting(waiting) where waiting.generation == generation && waiting.presentation == .guided:
            return .waitingForGrant
        case let .waiting(waiting) where waiting.generation == generation:
            state = .waiting(Waiting(
                generation: generation,
                presentation: .guided,
                pollTask: waiting.pollTask
            ))
            settings.openAccessibility()
            overlay.present(applicationURL: applicationURL)
            return .waitingForGrant
        case .idle, .waiting, .granted, .ended:
            startWaiting(generation: generation, presentation: .guided)
            settings.openAccessibility()
            overlay.present(applicationURL: applicationURL)
            return .waitingForGrant
        }
    }

    func beginSilent(for generation: UInt64) {
        if case let .waiting(waiting) = state, waiting.generation == generation {
            return
        }
        startWaiting(generation: generation, presentation: .silent)
    }

    func refreshGrant() {
        guard case let .waiting(waiting) = state else { return }
        settings.refreshOwnership()
        guard trust.isGranted else { return }

        waiting.pollTask.cancel()
        state = .granted(generation: waiting.generation)
        if waiting.presentation == .guided {
            overlay.dismiss()
            settings.closeOwnedWindow()
        }
        onGranted(waiting.generation)
    }

    func end(_ reason: AccessibilityPermissionEndReason = .superseded) {
        if case .ended = state { return }
        let generation = activeGeneration
        if case let .waiting(waiting) = state {
            waiting.pollTask.cancel()
            if waiting.presentation == .guided {
                overlay.dismiss()
            }
        }
        state = .ended(generation: generation, reason: reason)
    }

    private var activeGeneration: UInt64? {
        switch state {
        case .idle:
            nil
        case let .waiting(waiting):
            waiting.generation
        case let .granted(generation):
            generation
        case let .ended(generation, _):
            generation
        }
    }

    private func startWaiting(generation: UInt64, presentation: Presentation) {
        cancelWaitingForReplacement()
        let task = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .seconds(1))
                } catch {
                    return
                }
                guard let self else { return }
                self.refreshGrant()
                guard case let .waiting(waiting) = self.state,
                      waiting.generation == generation else {
                    return
                }
            }
        }
        state = .waiting(Waiting(
            generation: generation,
            presentation: presentation,
            pollTask: task
        ))
    }

    private func cancelWaitingForReplacement() {
        guard case let .waiting(waiting) = state else { return }
        waiting.pollTask.cancel()
        if waiting.presentation == .guided {
            overlay.dismiss()
        }
    }

    private func completeWithoutCallback(generation: UInt64) {
        if case let .waiting(waiting) = state {
            waiting.pollTask.cancel()
            settings.refreshOwnership()
            if waiting.presentation == .guided {
                overlay.dismiss()
                settings.closeOwnedWindow()
            }
        }
        state = .granted(generation: generation)
    }
}
