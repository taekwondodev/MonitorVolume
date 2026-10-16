// swift-tools-version: 6.2

import PackageDescription

let package = Package(
    name: "MonitorRemoteProtocol",
    platforms: [
        .iOS(.v26),
        .macOS(.v15)
    ],
    products: [
        .library(name: "MonitorRemoteProtocol", targets: ["MonitorRemoteProtocol"])
    ],
    targets: [
        .target(name: "MonitorRemoteProtocol"),
        .testTarget(
            name: "MonitorRemoteProtocolTests",
            dependencies: ["MonitorRemoteProtocol"]
        )
    ]
)
