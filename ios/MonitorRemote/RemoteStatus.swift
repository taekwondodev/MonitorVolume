import SwiftUI

/// What the link last observed about reaching the Mac.
struct RemoteLinkObservation: Equatable {
    var isConnected = false
    var isLocalNetworkDenied = false
    var isOnWiFi = true
}

enum RemoteStatus: Equatable {
    case connected
    case noMacFound
    case notOnWiFi
    case localNetworkDenied

    init(_ observation: RemoteLinkObservation) {
        self = if observation.isConnected {
            .connected
        } else if observation.isLocalNetworkDenied {
            .localNetworkDenied
        } else if observation.isOnWiFi == false {
            .notOnWiFi
        } else {
            .noMacFound
        }
    }

    var label: LocalizedStringResource {
        switch self {
        case .connected: "Connected"
        case .noMacFound: "No Mac found"
        case .notOnWiFi: "iPhone not on Wi-Fi"
        case .localNetworkDenied: "Local Network access denied"
        }
    }

    var systemImage: String {
        switch self {
        case .connected: "desktopcomputer"
        case .noMacFound: "magnifyingglass"
        case .notOnWiFi: "wifi.slash"
        case .localNetworkDenied: "lock.fill"
        }
    }
}
