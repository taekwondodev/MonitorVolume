// swift-tools-version: 6.2

import PackageDescription

let package = Package(
    name: "ProArtVolume",
    platforms: [
        .macOS(.v15)
    ],
    products: [
        .executable(name: "ProArtVolume", targets: ["ProArtVolume"])
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
            name: "ProArtVolumeCore",
            dependencies: ["MonitorTransport"]
        ),
        .executableTarget(
            name: "ProArtVolume",
            dependencies: ["ProArtVolumeCore"]
        ),
        .testTarget(
            name: "ProArtVolumeTests",
            dependencies: ["ProArtVolume", "ProArtVolumeCore"]
        )
    ]
)
