import AppKit
import ProArtVolumeCore
import ServiceManagement

@MainActor
final class ApplicationCoordinator: NSObject, NSApplicationDelegate, MediaKeyInterceptorDelegate {
    private let eligibility: ControlEligibility
    private let service: IntentControlService
    private let output: CoreAudioOutputRepository
    private let interceptor: MediaKeyInterceptor
    private let osd: VolumeOSDPresenter
    private let diagnostics: InputLifecycleDiagnostics?
    private var reducer = VolumeIntentReducer()
    private var permissionTask: Task<Void, Never>?
    private var permissionPollingGeneration: UInt64 = 0
    private var permissionGrantWatch: Task<Void, Never>?
    private var outputObservation: ActiveAudioOutputObservation?
    private var sleeping = false
    private var stopped = false
    private var reopenAfterTapRelease = false

    init(service: IntentControlService, output: CoreAudioOutputRepository,
         eligibility: ControlEligibility, diagnostics: InputLifecycleDiagnostics?) {
        self.service = service
        self.output = output
        self.eligibility = eligibility
        self.diagnostics = diagnostics
        interceptor = MediaKeyInterceptor(eligibility: eligibility, diagnostics: diagnostics)
        osd = VolumeOSDPresenter()
        super.init()
        interceptor.delegate = self
    }

    isolated deinit {
        stopped = true
        reopenAfterTapRelease = false
        stopPermissionPolling()
        interceptor.stop(reason: .deinitialization)
        NotificationCenter.default.removeObserver(self)
        NSWorkspace.shared.notificationCenter.removeObserver(self)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        diagnostics?.record(.lifecycle(.launch, generation: eligibility.generation))
        observeOutput()
        NotificationCenter.default.addObserver(self, selector: #selector(displayChanged),
                                               name: NSApplication.didChangeScreenParametersNotification, object: nil)
        let workspace = NSWorkspace.shared.notificationCenter
        workspace.addObserver(self, selector: #selector(willSleep), name: NSWorkspace.willSleepNotification, object: nil)
        workspace.addObserver(self, selector: #selector(didWake), name: NSWorkspace.didWakeNotification, object: nil)
        reopen()
        registerAtLoginOnFirstLaunch()
    }

    private func registerAtLoginOnFirstLaunch() {
        let defaults = UserDefaults.standard
        let key = "launchAtLoginRegistrationAttempted"
        guard !defaults.bool(forKey: key) else { return }
        defaults.set(true, forKey: key)
        _ = defaults.synchronize()
        try? SMAppService.mainApp.register()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        reopen()
        return false
    }

    func applicationWillTerminate(_ notification: Notification) {
        diagnostics?.record(.lifecycle(.termination, generation: eligibility.generation))
        stopped = true
        reopenAfterTapRelease = false
        stopPermissionPolling()
        stopWatchingForPermissionGrant()
        outputObservation = nil
        let generation = eligibility.invalidate()
        interceptor.stop(reason: .termination)
        scheduleServiceValidation(generation: generation, reason: .termination, permitted: false)
        diagnostics?.record(.sessionEnded)
    }

    private func reopen() {
        guard !stopped, !sleeping else { return }
        guard case let .started(generation) = eligibility.reopen() else {
            if eligibility.phase.isSuspended {
                reopenAfterTapRelease = true
            }
            return
        }
        reopenAfterTapRelease = false
        diagnostics?.record(.lifecycle(.reopen, generation: generation))
        interceptor.requestPermissions()
        guard interceptor.open(generation: generation, permissionFailure: .missingPermission) else { return }
        startPermissionPolling()
        scheduleServiceValidation(generation: generation, reason: .reopen, permitted: true)
    }

    private func observePermission() {
        let poll = diagnostics?.begin(.permissionPoll, reason: .permissionPoll)
        defer { diagnostics?.end(poll) }
        guard !sleeping, !stopped else {
            diagnostics?.record(.pollSkipped(sleeping ? .sleeping : .stopped))
            return
        }
        guard eligibility.allowsPermissionPolling else {
            stopPermissionPolling()
            return
        }
        guard interceptor.validateActive(generation: eligibility.generation) else {
            stopPermissionPolling()
            return
        }
    }

    private func startPermissionPolling() {
        guard permissionTask == nil else { return }
        permissionPollingGeneration &+= 1
        let pollingGeneration = permissionPollingGeneration
        permissionTask = Task { @MainActor [weak self] in
            defer {
                if let self, self.permissionPollingGeneration == pollingGeneration {
                    self.permissionTask = nil
                }
            }
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .seconds(1))
                } catch {
                    return
                }
                guard let self,
                      !self.stopped,
                      !self.sleeping,
                      self.eligibility.allowsPermissionPolling else {
                    return
                }
                self.observePermission()
            }
        }
    }

    private func stopPermissionPolling() {
        permissionPollingGeneration &+= 1
        permissionTask?.cancel()
        permissionTask = nil
    }

    private func watchForPermissionGrant() {
        guard permissionGrantWatch == nil, eligibility.awaitsPermission else { return }
        permissionGrantWatch = Task { @MainActor [weak self] in
            defer { self?.permissionGrantWatch = nil }
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .seconds(1))
                } catch {
                    return
                }
                guard let self, !self.stopped, !self.sleeping else { return }
                guard self.eligibility.awaitsPermission else { return }
                guard self.interceptor.hasAccessibility else { continue }
                self.diagnostics?.record(.lifecycle(.permissionGranted, generation: self.eligibility.generation))
                self.reopen()
                return
            }
        }
    }

    private func stopWatchingForPermissionGrant() {
        permissionGrantWatch?.cancel()
        permissionGrantWatch = nil
    }

    private func revalidateHardware(reason: InputLifecycleReason) {
        guard !stopped, !sleeping, eligibility.allowsPermissionPolling else { return }
        let generation = eligibility.invalidate()
        scheduleServiceValidation(generation: generation, reason: reason, permitted: true)
    }

    private func scheduleServiceValidation(generation: UInt64, reason: InputLifecycleReason, permitted: Bool) {
        diagnostics?.record(.revalidation(.entered, reason, generation: generation))
        guard generation == eligibility.generation else {
            diagnostics?.record(.revalidation(.staleDiscarded, reason, generation: generation))
            return
        }
        let permitted = permitted && !stopped && !sleeping && eligibility.phase.isLifecycleActive
        let service = service
        Task { await service.revalidate(generation: generation, permitted: permitted) }
        diagnostics?.record(.revalidation(.serviceScheduled, reason, generation: generation))
    }

    private func observeOutput() {
        guard outputObservation == nil else { return }
        let eligibility = eligibility
        outputObservation = try? output.observeDefaultOutputChanges { [weak self, eligibility] in
            Task { @MainActor [weak self] in
                guard let self,
                      eligibility.allowsPermissionPolling,
                      !self.stopped,
                      !self.sleeping else { return }
                self.diagnostics?.record(.lifecycle(.outputChanged, generation: eligibility.generation))
                self.revalidateHardware(reason: .outputChanged)
            }
        }
    }

    @objc private func displayChanged() {
        guard !stopped, !sleeping, eligibility.allowsPermissionPolling else { return }
        diagnostics?.record(.lifecycle(.displayChanged, generation: eligibility.generation))
        revalidateHardware(reason: .displayChanged)
    }

    @objc private func willSleep() {
        guard !stopped, !sleeping else { return }
        sleeping = true
        stopPermissionPolling()
        stopWatchingForPermissionGrant()
        let generation = eligibility.sleep()
        diagnostics?.record(.lifecycle(.sleep, generation: generation))
        interceptor.stop(reason: .sleep)
        scheduleServiceValidation(generation: generation, reason: .sleep, permitted: false)
    }

    @objc private func didWake() {
        guard sleeping, !stopped else { return }
        sleeping = false
        switch eligibility.wake() {
        case let .revalidate(generation):
            diagnostics?.record(.lifecycle(.wake, generation: generation))
            guard interceptor.open(generation: generation, permissionFailure: .permissionRevoked) else { return }
            startPermissionPolling()
            scheduleServiceValidation(generation: generation, reason: .wake, permitted: true)
        case .waitingForTapRelease:
            diagnostics?.record(.lifecycle(.wake, generation: eligibility.generation))
        case .remainsSuspended:
            stopPermissionPolling()
            diagnostics?.record(.lifecycle(.wake, generation: eligibility.generation))
            if reopenAfterTapRelease {
                reopenAfterTapRelease = false
                reopen()
            }
            watchForPermissionGrant()
        case .remainsUnavailable:
            stopPermissionPolling()
            diagnostics?.record(.lifecycle(.wake, generation: eligibility.generation))
        case .ignored:
            diagnostics?.record(.lifecycle(.wake, generation: eligibility.generation))
            if eligibility.allowsPermissionPolling {
                startPermissionPolling()
            }
        }
    }

    func mediaKeyInterceptor(_ interceptor: MediaKeyInterceptor, requestedSuspension reason: InputSuspensionReason) {
        stopPermissionPolling()
        let generation = eligibility.generation
        let lifecycleReason = Self.lifecycleReason(for: reason)
        diagnostics?.record(.revalidation(.requested, lifecycleReason, generation: generation))
        interceptor.stop(reason: lifecycleReason)
        scheduleServiceValidation(generation: generation, reason: lifecycleReason, permitted: false)
        watchForPermissionGrant()
    }

    func mediaKeyInterceptorDidReleaseTap(_ interceptor: MediaKeyInterceptor) {
        guard reopenAfterTapRelease, !sleeping else { return }
        reopenAfterTapRelease = false
        reopen()
    }

    func mediaKeyInterceptor(_ interceptor: MediaKeyInterceptor, received delivery: AdmittedMediaKey) {
        let command = delivery.command
        let session = delivery.session
        let prior = reducer.startingIntent(for: session)
        let request = reducer.accept(command, session: session)
        osd.show(request.intent, displayName: session.target.displayName, boundary: request.intent == prior)
        let service = service
        Task { await service.submit(request) }
    }

    private static func lifecycleReason(for reason: InputSuspensionReason) -> InputLifecycleReason {
        switch reason {
        case .missingPermission:
            .missingAccessibility
        case .permissionRevoked:
            .permissionRevoked
        case .tapDisabledByTimeout, .tapDisabledByUserInput:
            .disabledTap
        case .tapCreationFailed:
            .creationFailure
        }
    }
}
