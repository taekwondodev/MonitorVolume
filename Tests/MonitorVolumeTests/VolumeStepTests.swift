import Testing
@testable import MonitorVolumeCore

struct VolumeStepTests {
    @Test(arguments: [
        (0, VolumeStep.decrease, 0),
        (100, VolumeStep.increase, 100),
        (95, VolumeStep.increase, 100),
        (5, VolumeStep.decrease, 0),
    ])
    func appliesSaturatingFivePointStep(start: Int, step: VolumeStep, expected: Int) throws {
        let volume = try #require(VolumeLevel(start))

        #expect(volume.adjusting(by: step.points).rawValue == expected)
    }
}
