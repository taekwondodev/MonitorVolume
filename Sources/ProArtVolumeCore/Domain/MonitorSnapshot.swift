package struct MonitorSnapshot: Equatable, Sendable {
    package let revision: UInt64
    package let status: MonitorStatus

    package init(revision: UInt64, status: MonitorStatus) {
        self.revision = revision
        self.status = status
    }
}
