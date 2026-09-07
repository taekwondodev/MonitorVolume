import AppKit
import ProArtVolumeCore

@MainActor
final class ApplicationCoordinator: NSObject, NSApplicationDelegate, MediaKeyInterceptorDelegate {
    private let eligibility: ControlEligibility
    private let service: IntentControlService
    private let output: CoreAudioOutputRepository
    private let interceptor: MediaKeyInterceptor
    private let osd: VolumeOSDPresenter
    private let recorder: LatencyRecorder?
    private let diagnostics: InputLifecycleDiagnostics?
    private var reducer = VolumeIntentReducer()
    private var permissionTask: Task<Void, Never>?
    private var outputObservation: ActiveAudioOutputObservation?
    private var permitted = false
    private var sleeping = false
    private var stopped = false

    init(service: IntentControlService, output: CoreAudioOutputRepository,
         eligibility: ControlEligibility, recorder: LatencyRecorder?, diagnostics: InputLifecycleDiagnostics?) {
        self.service = service
        self.output = output
        self.eligibility = eligibility
        self.recorder = recorder
        self.diagnostics = diagnostics
        interceptor = MediaKeyInterceptor(eligibility: eligibility, diagnostics: diagnostics)
        osd = VolumeOSDPresenter(latencyRecorder: recorder)
        super.init()
        interceptor.delegate = self
    }

    isolated deinit {
        permissionTask?.cancel()
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
        permissionTask = Task { [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(1)) } catch { return }
                self?.observePermission()
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        reopen()
        return false
    }

    func applicationWillTerminate(_ notification: Notification) {
        diagnostics?.record(.lifecycle(.termination, generation: eligibility.generation))
        stopped = true
        permissionTask?.cancel()
        permissionTask = nil
        outputObservation = nil
        interceptor.stop(reason: .termination)
        revalidate(generation: eligibility.invalidate(), reason: .termination)
        diagnostics?.record(.sessionEnded)
    }

    private func reopen() {
        diagnostics?.record(.lifecycle(.reopen, generation: eligibility.generation))
        interceptor.requestPermissions()
        revalidate(generation: eligibility.invalidate(), reason: .reopen)
    }

    private func observePermission() {
        let poll = diagnostics?.begin(.permissionPoll, reason: .permissionPoll)
        defer { diagnostics?.end(poll) }
        guard !sleeping, !stopped else {
            diagnostics?.record(.pollSkipped(sleeping ? .sleeping : .stopped))
            return
        }
        observeOutput()
        let available = interceptor.refreshPermissions()
        if available != permitted || outputObservation == nil {
            revalidate(generation: eligibility.invalidate(), reason: .permissionPoll)
        }
    }

    private func revalidate(generation: UInt64, reason: InputLifecycleReason) {
        diagnostics?.record(.revalidation(.entered, reason, generation: generation))
        guard generation == eligibility.generation else {
            diagnostics?.record(.revalidation(.staleDiscarded, reason, generation: generation))
            return
        }
        permitted = !stopped && !sleeping && interceptor.refreshPermissions() && outputObservation != nil
        let service = service
        let permitted = permitted
        Task { await service.revalidate(generation: generation, permitted: permitted) }
        diagnostics?.record(.revalidation(.serviceScheduled, reason, generation: generation))
    }

    private func observeOutput() {
        guard outputObservation == nil else { return }
        let eligibility = eligibility
        outputObservation = try? output.observeDefaultOutputChanges { [weak self, eligibility] in
            let generation = eligibility.invalidate()
            Task { @MainActor [weak self] in
                self?.diagnostics?.record(.lifecycle(.outputChanged, generation: generation))
                self?.revalidate(generation: generation, reason: .outputChanged)
            }
        }
    }

    @objc private func displayChanged() {
        diagnostics?.record(.lifecycle(.displayChanged, generation: eligibility.generation))
        revalidate(generation: eligibility.invalidate(), reason: .displayChanged)
    }

    @objc private func willSleep() {
        diagnostics?.record(.lifecycle(.sleep, generation: eligibility.generation))
        sleeping = true
        interceptor.stop(reason: .sleep)
        revalidate(generation: eligibility.invalidate(), reason: .sleep)
    }

    @objc private func didWake() {
        diagnostics?.record(.lifecycle(.wake, generation: eligibility.generation))
        sleeping = false
        revalidate(generation: eligibility.invalidate(), reason: .wake)
    }

    func mediaKeyInterceptorBecameUnavailable(_ interceptor: MediaKeyInterceptor) {
        let generation = eligibility.invalidate()
        permitted = false
        diagnostics?.record(.revalidation(.requested, .tapUnavailable, generation: generation))
        Task { @MainActor [weak self] in self?.revalidate(generation: generation, reason: .tapUnavailable) }
    }

    func mediaKeyInterceptor(_ interceptor: MediaKeyInterceptor, received command: MediaKeyCommand, session: ControlSession) {
        let prior = reducer.startingIntent(for: session)
        let id = recorder?.beginInteraction(command: command, startingMuted: prior.mute == .muted)
        let request = reducer.accept(command, session: session, measurementID: id)
        let ids = id.map { [$0] } ?? []
        recorder?.record(stage: .intentReduced, interactionIDs: ids)
        osd.show(request.intent, boundary: request.intent == prior, interactionIDs: ids)
        recorder?.record(stage: .commandEnqueueRequested, interactionIDs: ids)
        let service = service
        Task { await service.submit(request) }
    }
}
