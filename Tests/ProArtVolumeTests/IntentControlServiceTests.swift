import Testing
@testable import ProArtVolumeCore

struct IntentControlServiceTests {
    @Test func coalescesCompleteStatesWithoutOverlappingHardware() async throws {
        let rig = try ControlRig(volume: 50)
        await rig.start()
        let session = try #require(rig.eligibility.session)
        var reducer = VolumeIntentReducer()
        await rig.monitor.holdNextWrite()
        await rig.service.submit(reducer.accept(.step(.increase), session: session))
        await rig.monitor.waitForHeldWrite()
        await rig.service.submit(reducer.accept(.step(.increase), session: session))
        await rig.service.submit(reducer.accept(.step(.increase), session: session))
        await rig.monitor.releaseWrite()
        await rig.service.waitForIdle()
        #expect(await rig.monitor.writtenVolumes == [55, 65])
        #expect(await rig.monitor.maximumConcurrentOperations == 1)
    }

    @Test func rejectsOutOfOrderSubmissionsAndCancelsPendingMuteParity() async throws {
        let rig = try ControlRig(volume: 50)
        await rig.start()
        let session = try #require(rig.eligibility.session)
        var reducer = VolumeIntentReducer()
        await rig.monitor.holdNextWrite()
        await rig.service.submit(reducer.accept(.step(.increase), session: session))
        await rig.monitor.waitForHeldWrite()
        let older = reducer.accept(.toggleMute, session: session)
        let newer = reducer.accept(.toggleMute, session: session)
        await rig.service.submit(newer)
        await rig.service.submit(older)
        await rig.monitor.releaseWrite()
        await rig.service.waitForIdle()
        #expect(await rig.monitor.writtenMutes.isEmpty)
        #expect(await rig.monitor.writtenVolumes == [55])
    }

    @Test(arguments: [MonitorRepositoryError.writeFailure, .readFailure, .malformedResponse, .readBackMismatch])
    func failureDiscardsNewerPendingIntentAndRecoversReadOnly(error: MonitorRepositoryError) async throws {
        let rig = try ControlRig(volume: 50)
        await rig.start()
        let session = try #require(rig.eligibility.session)
        var reducer = VolumeIntentReducer()
        await rig.monitor.holdNextWrite(error: error)
        await rig.service.submit(reducer.accept(.step(.increase), session: session))
        await rig.monitor.waitForHeldWrite()
        await rig.service.submit(reducer.accept(.toggleMute, session: session))
        await rig.monitor.releaseWrite()
        await rig.service.waitForIdle()
        #expect(rig.eligibility.session == nil)
        #expect(await rig.timer.nextDelay() == .seconds(2))
        #expect(await rig.monitor.writtenMutes.isEmpty)
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        let recovered = try #require(rig.eligibility.session)
        #expect(recovered != session)
        await rig.service.submit(reducer.accept(.toggleMute, session: session))
        await rig.service.waitForIdle()
        #expect(await rig.monitor.writtenMutes.isEmpty)
        #expect(await rig.monitor.writtenVolumes == [55])
    }

    @Test(arguments: [MonitorRepositoryError.writeFailure, nil])
    func invalidationDuringWriteStopsStaleWorkFromApplying(error: MonitorRepositoryError?) async throws {
        let rig = try ControlRig(volume: 50, mute: .muted)
        await rig.start()
        let session = try #require(rig.eligibility.session)
        var reducer = VolumeIntentReducer()
        await rig.monitor.holdNextWrite(error: error)
        await rig.service.submit(reducer.accept(.step(.increase), session: session))
        await rig.monitor.waitForHeldWrite()
        let generation = rig.eligibility.invalidate()
        await rig.service.revalidate(generation: generation, permitted: true)
        await rig.monitor.releaseWrite()
        await rig.service.waitForIdle()
        #expect(rig.eligibility.session?.generation == generation)
        #expect(await rig.monitor.writtenMutes.isEmpty)
        #expect(await rig.monitor.maximumConcurrentOperations == 1)
        #expect(await rig.timer.requestCount == 0)
    }

    @Test func partialSuccessStopsAndReseedsActualState() async throws {
        let rig = try ControlRig(volume: 50, mute: .muted)
        await rig.start()
        let session = try #require(rig.eligibility.session)
        await rig.monitor.failMute()
        var reducer = VolumeIntentReducer()
        await rig.service.submit(reducer.accept(.step(.increase), session: session))
        await rig.service.waitForIdle()
        #expect(rig.eligibility.session == nil)
        #expect(await rig.monitor.writtenVolumes == [55])
        #expect(await rig.monitor.writtenMutes == [.unmuted])
        #expect(await rig.timer.nextDelay() == .seconds(2))
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        #expect(rig.eligibility.session?.seed.volume.rawValue == 55)
        #expect(rig.eligibility.session?.seed.mute == .muted)
        #expect(await rig.monitor.writtenMutes == [.unmuted])
    }

    @Test func recoveryRetriesWithGrowingBackoffAndResetsAfterSuccess() async throws {
        let rig = try ControlRig(volume: 50)
        await rig.monitor.setReadable(false)
        await rig.start()
        for expected in [2, 5, 10, 30, 30] {
            #expect(await rig.timer.nextDelay() == .seconds(expected))
            await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        }
        #expect(await rig.timer.nextDelay() == .seconds(30))
        await rig.monitor.setReadable(true)
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        let session = try #require(rig.eligibility.session)
        var reducer = VolumeIntentReducer()
        await rig.monitor.failMute()
        await rig.service.submit(reducer.accept(.toggleMute, session: session))
        await rig.service.waitForIdle()
        #expect(await rig.timer.nextDelay() == .seconds(2))
    }

    @Test func lifecycleRevalidationRestartsBackoffDespitePersistentFailure() async throws {
        let rig = try ControlRig(volume: 50)
        await rig.monitor.setReadable(false)
        await rig.start()
        #expect(await rig.timer.nextDelay() == .seconds(2))
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        #expect(await rig.timer.nextDelay() == .seconds(5))
        #expect(await rig.monitor.readCount == 2)

        await rig.monitor.holdNextRead()
        let generation = rig.eligibility.invalidate()
        await rig.service.waitForRecoveryAttempt {
            await rig.service.revalidate(generation: generation, permitted: true)
            await rig.monitor.waitForHeldRead()
            #expect(await rig.monitor.readCount == 3)
            #expect(rig.eligibility.session == nil)
            await rig.timer.advance()
            await rig.monitor.releaseRead()
        }
        #expect(await rig.timer.nextDelay() == .seconds(2))
        #expect(await rig.monitor.readCount == 3)
        #expect(rig.eligibility.session == nil)
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        #expect(await rig.timer.nextDelay() == .seconds(5))
        #expect(await rig.monitor.readCount == 4)

        await rig.monitor.setReadable(true)
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        #expect(rig.eligibility.session?.generation == generation)
        #expect(await rig.monitor.readCount == 5)
        #expect(await rig.monitor.maximumConcurrentOperations == 1)
        #expect(await rig.monitor.writtenVolumes.isEmpty)
        #expect(await rig.monitor.writtenMutes.isEmpty)
    }

    @Test func absentPermissionOrInactiveOutputPreventsReadsAndCommands() async throws {
        let rig = try ControlRig(volume: 50)
        let generation = rig.eligibility.invalidate()
        await rig.service.revalidate(generation: generation, permitted: false)
        await rig.service.waitForIdle()
        #expect(await rig.monitor.readCount == 0)
        await rig.output.setActive(false)
        await rig.start()
        #expect(await rig.monitor.readCount == 0)
        #expect(rig.eligibility.session == nil)
    }

    @Test(arguments: [MonitorRepositoryError.readFailure, .malformedResponse])
    func failedInitialAndRecoveryReadsRemainUnready(error: MonitorRepositoryError) async throws {
        let rig = try ControlRig(volume: 50)
        await rig.monitor.failNextRead(error)
        await rig.start()
        #expect(rig.eligibility.session == nil)
        #expect(await rig.timer.nextDelay() == .seconds(2))
        #expect(await rig.monitor.readCount == 1)
        await rig.monitor.failNextRead(error)
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        #expect(rig.eligibility.session == nil)
        #expect(await rig.timer.nextDelay() == .seconds(5))
        #expect(await rig.monitor.readCount == 2)
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        #expect(rig.eligibility.session?.seed.volume.rawValue == 50)
        #expect(await rig.monitor.writtenVolumes.isEmpty)
        #expect(await rig.monitor.writtenMutes.isEmpty)
    }

    @Test func invalidationDuringReadDoesNotAcceptStaleSuccess() async throws {
        let rig = try ControlRig(volume: 50)
        await rig.monitor.holdNextRead()
        await rig.service.revalidate(generation: rig.eligibility.invalidate(), permitted: true)
        await rig.monitor.waitForHeldRead()
        let current = rig.eligibility.invalidate()
        await rig.service.revalidate(generation: current, permitted: true)
        #expect(rig.eligibility.session == nil)
        #expect(await rig.monitor.readCount == 1)
        await rig.monitor.releaseRead()
        await rig.service.waitForIdle()
        #expect(rig.eligibility.session?.generation == current)
        #expect(await rig.monitor.readCount == 2)
        #expect(await rig.monitor.maximumConcurrentOperations == 1)
    }

    @Test func outputLossDuringReadPreventsTrustedSeed() async throws {
        let rig = try ControlRig(volume: 50)
        await rig.monitor.holdNextRead()
        await rig.service.revalidate(generation: rig.eligibility.invalidate(), permitted: true)
        await rig.monitor.waitForHeldRead()
        await rig.output.setActive(false)
        await rig.monitor.releaseRead()
        await rig.service.waitForIdle()
        #expect(rig.eligibility.session == nil)
        #expect(await rig.monitor.writtenVolumes.isEmpty)
        #expect(await rig.timer.requestCount == 0)
    }

    @Test func outputLossDuringVolumeWritePreventsUnmute() async throws {
        let rig = try ControlRig(volume: 50, mute: .muted)
        await rig.start()
        let session = try #require(rig.eligibility.session)
        var reducer = VolumeIntentReducer()
        await rig.monitor.holdNextWrite()
        await rig.service.submit(reducer.accept(.step(.increase), session: session))
        await rig.monitor.waitForHeldWrite()
        await rig.output.setActive(false)
        await rig.monitor.releaseWrite()
        await rig.service.waitForIdle()
        #expect(rig.eligibility.session == nil)
        #expect(await rig.monitor.writtenVolumes == [55])
        #expect(await rig.monitor.writtenMutes.isEmpty)
    }

    @Test func permissionLossCancelsRecoveryWithoutNewReads() async throws {
        let rig = try ControlRig(volume: 50)
        await rig.monitor.setReadable(false)
        await rig.start()
        #expect(await rig.timer.nextDelay() == .seconds(2))
        let generation = rig.eligibility.invalidate()
        await rig.service.revalidate(generation: generation, permitted: false)
        await rig.service.waitForRecoveryAttempt { await rig.timer.advance() }
        #expect(await rig.monitor.readCount == 1)
        #expect(rig.eligibility.session == nil)
    }
}
