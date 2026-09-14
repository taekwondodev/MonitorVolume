// swift-tools-version: 6.2

import PackageDescription

let package = Package(
    name: "MonitorVolume",
    platforms: [
        .macOS(.v15)
    ],
    products: [
        .executable(name: "MonitorVolume", targets: ["MonitorVolume"])
    ],
    targets: [
        .target(
            name: "MonitorTransport",
            linkerSettings: [
                .linkedFramework("CoreFoundation"),
                .linkedFramework("IOKit")
            ]
        ),
        .target(
            name: "MonitorVolumeCore",
            dependencies: ["MonitorTransport"]
        ),
        .executableTarget(
            name: "MonitorVolume",
            dependencies: ["MonitorVolumeCore"]
        ),
        .testTarget(
            name: "MonitorVolumeTests",
            dependencies: ["MonitorVolume", "MonitorVolumeCore"]
        )
    ]
)
