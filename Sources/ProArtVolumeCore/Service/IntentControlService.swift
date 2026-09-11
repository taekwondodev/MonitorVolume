package actor IntentControlService {
    private let monitor: any MonitorControlling
    private let activeOutput: any ActiveAudioOutputReading
    private let eligibility: ControlEligibility
    private let sleeper: ControlSleeper

    private var generation: UInt64 = 0
    private var permitted = false
    private var seedRevision: UInt64 = 0
    private var latestRevision: UInt64 = 0
    private var confirmed: ConfirmedMonitorState?
    private var desired: DesiredMonitorState?
    private var needsRead = false
    private var worker: Task<Void, Never>?
    private var recovery: Task<Void, Never>?
    private var recoveryRevision: UInt64 = 0
    private var backoff = RecoveryDelay()

    package init(
        monitor: any MonitorControlling,
        activeOutput: any ActiveAudioOutputReading,
        eligibility: ControlEligibility,
        sleeper: ControlSleeper = .continuous
    ) {
        self.monitor = monitor
        self.activeOutput = activeOutput
        self.eligibility = eligibility
        self.sleeper = sleeper
    }

    deinit {
        recovery?.cancel()
        worker?.cancel()
    }

    @discardableResult
    package func revalidate(generation: UInt64, permitted: Bool) -> Bool {
        guard eligibility.generation == generation else { return false }
        cancelRecovery()
        self.generation = generation
        self.permitted = permitted
        confirmed = nil
        discardDesired()
        backoff = RecoveryDelay()
        latestRevision = 0
        needsRead = false
        guard permitted, eligibility.beginValidation(generation: generation) else { return false }
        needsRead = true
        startWorker()
        return true
    }

    package func submit(_ request: DesiredMonitorState) {
        guard isCurrent(request.session.generation),
              eligibility.contains(request.session),
              request.revision > latestRevision else {
            return
        }
        latestRevision = request.revision
        desired = request
        startWorker()
    }

    package func waitForIdle() async {
        while let worker { await worker.value }
    }

    package func waitForRecoveryAttempt(resumingWith resume: @Sendable () async -> Void) async {
        let attempt = recovery
        await resume()
        await attempt?.value
        await waitForIdle()
    }

    private func isCurrent(_ generation: UInt64) -> Bool {
        permitted
            && self.generation == generation
            && eligibility.generation == generation
            && eligibility.phase.isLifecycleActive
    }

    private func startWorker() {
        guard worker == nil, needsRead || desired != nil else { return }
        worker = Task { await drain() }
    }

    private func drain() async {
        while needsRead || desired != nil {
            if needsRead {
                needsRead = false
                await readTrustedState(generation: generation)
            } else if let request = desired {
                desired = nil
                await reconcile(request)
            }
        }
        worker = nil
    }

    private func readTrustedState(generation: UInt64) async {
        guard isCurrent(generation) else { return }
        do {
            guard try await activeOutput.isTargetActive(), isCurrent(generation) else { return }
            guard let state = try await monitor.readState() else {
                fail(generation: generation)
                return
            }
            guard isCurrent(generation) else { return }
            guard try await activeOutput.isTargetActive(), isCurrent(generation) else { return }
            confirmed = state
            seedRevision += 1
            eligibility.publish(ControlSession(generation: generation, seedRevision: seedRevision, seed: state))
            backoff = RecoveryDelay()
            cancelRecovery()
        } catch {
            fail(generation: generation)
        }
    }

    private enum ReconcileOutcome {
        case completed, superseded, discarded
    }

    @discardableResult
    private func reconcile(_ request: DesiredMonitorState) async -> ReconcileOutcome {
        guard isCurrent(request.session.generation), eligibility.contains(request.session),
              var state = confirmed else { return .discarded }
        do {
            guard try await mayWrite(request.session) else { return .discarded }
            if desired != nil { return .superseded }
            if request.intent.volume != state.volume {
                let volume = try await monitor.writeVolume(request.intent.volume)
                guard isCurrent(request.session.generation) else { return .discarded }
                guard volume == request.intent.volume else { throw MonitorRepositoryError.readBackMismatch }
                state = ConfirmedMonitorState(volume: volume, mute: state.mute)
                confirmed = state
            }
            if desired != nil { return .superseded }
            if request.intent.mute != state.mute {
                guard try await mayWrite(request.session) else { return .discarded }
                if desired != nil { return .superseded }
                let mute = try await monitor.writeMute(request.intent.mute)
                guard isCurrent(request.session.generation) else { return .discarded }
                guard mute == request.intent.mute else { throw MonitorRepositoryError.readBackMismatch }
                state = ConfirmedMonitorState(volume: state.volume, mute: mute)
                confirmed = state
            }
            return isCurrent(request.session.generation) ? .completed : .discarded
        } catch {
            fail(generation: request.session.generation)
            return .discarded
        }
    }

    private func mayWrite(_ session: ControlSession) async throws(MonitorRepositoryError) -> Bool {
        guard isCurrent(session.generation), eligibility.contains(session) else { return false }
        let active = try await activeOutput.isTargetActive()
        guard isCurrent(session.generation), eligibility.contains(session) else { return false }
        if !active {
            eligibility.markUnavailable(generation: session.generation)
            discardDesired()
            confirmed = nil
        }
        return active
    }

    private func fail(generation: UInt64) {
        guard isCurrent(generation) else { return }
        eligibility.markUnavailable(generation: generation)
        discardDesired()
        confirmed = nil
        scheduleRecovery(generation: generation)
    }

    private func discardDesired() {
        desired = nil
    }

    private func cancelRecovery() {
        recovery?.cancel()
        recovery = nil
        recoveryRevision += 1
    }

    private func scheduleRecovery(generation: UInt64) {
        guard recovery == nil else { return }
        let delay = backoff.next()
        let sleeper = sleeper
        let revision = recoveryRevision
        recovery = Task { [weak self] in
            do { try await sleeper.sleep(for: delay) } catch { return }
            guard !Task.isCancelled else { return }
            await self?.retryRead(generation: generation, revision: revision)
        }
    }

    private func retryRead(generation: UInt64, revision: UInt64) {
        guard isCurrent(generation), recoveryRevision == revision else { return }
        recovery = nil
        guard eligibility.beginValidation(generation: generation) else { return }
        needsRead = true
        startWorker()
    }
}
