import Observation
import ProArtVolumeCore

@MainActor
@Observable
final class MonitorStatusModel {
    private let service: VolumeControlService

    private(set) var status: MonitorStatus?

    init(service: VolumeControlService) {
        self.service = service
    }

    func refresh() async {
        status = await service.refresh()
    }
}
